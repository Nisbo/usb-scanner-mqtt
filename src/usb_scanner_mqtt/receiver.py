"""Linux input reader and durable MQTT outbox, independent of any dashboard."""
import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .keyboard import Decoder

LOG = logging.getLogger(__name__)


def scan_payload(text, scanner_id):
    return {"ean": text, "scanner": scanner_id, "scan_id": uuid.uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat()}


def discovery(config):
    scanner, mqtt = config["scanner"], config["mqtt"]
    identity = config["installation_id"] + "_" + scanner["id"]
    base = "usb-scanner-mqtt/" + config["installation_id"]
    topic = f"{mqtt['discovery_prefix'].rstrip('/')}/sensor/{identity}/barcode/config"
    return topic, {
        "name": "Last scan", "unique_id": identity + "_barcode",
        "state_topic": scanner["topic"],
        # HA states have a length limit; full QR text stays in attributes.
        "value_template": "{{ value_json.ean if value_json.ean | length <= 255 else 'QR scan' }}",
        "json_attributes_topic": scanner["topic"],
        "json_attributes_template": "{{ {'scan_id': value_json.scan_id, 'scanner': value_json.scanner, 'timestamp': value_json.timestamp, 'barcode': value_json.ean} | tojson }}",
        "availability_topic": base + "/availability",
        "payload_available": "online", "payload_not_available": "offline",
        "icon": "mdi:barcode-scan", "qos": 1,
        "device": {"identifiers": [identity], "name": scanner["name"],
                   "manufacturer": "Nisbo", "model": "USB HID MQTT Scanner",
                   "sw_version": __version__},
    }


class Outbox:
    """Commit scans before transmission. IDs survive disconnects and restarts."""
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        try:
            self.connection.execute("CREATE TABLE IF NOT EXISTS outbox (sequence INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL)")
            self.connection.commit()
        except BaseException:
            self.connection.close()
            raise

    def put(self, topic, payload):
        with self.lock, self.connection:
            count = self.connection.execute("SELECT count(*) FROM outbox").fetchone()[0]
            if count >= 1000:
                raise RuntimeError("Outbox full (1000 scans). Restore MQTT before scanning more.")
            self.connection.execute("INSERT INTO outbox(topic,payload) VALUES (?,?)",
                                    (topic, json.dumps(payload, ensure_ascii=False)))

    def first(self):
        with self.lock:
            return self.connection.execute("SELECT sequence,topic,payload FROM outbox ORDER BY sequence LIMIT 1").fetchone()

    def remove(self, sequence):
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM outbox WHERE sequence=?", (sequence,))

    def count(self):
        with self.lock:
            return self.connection.execute("SELECT count(*) FROM outbox").fetchone()[0]

    def close(self):
        with self.lock:
            self.connection.close()


class Publisher:
    def __init__(self, config, outbox):
        import paho.mqtt.client as mqtt
        self.config = config
        self.outbox = outbox
        self.stop = threading.Event()
        self.connected = threading.Event()
        self.device_connected = threading.Event()
        self.scan_gate = threading.RLock()
        self.test_paused = threading.Event()
        self.publish_lock = threading.Lock()
        self.pending_mid = None
        self.pending_ack = threading.Event()
        self.availability = "usb-scanner-mqtt/" + config["installation_id"] + "/availability"
        kwargs = {"client_id": "usb-scanner-" + config["installation_id"], "protocol": mqtt.MQTTv5}
        if hasattr(mqtt, "CallbackAPIVersion"):
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        self.client = mqtt.Client(**kwargs)
        broker = config["mqtt"]
        if broker["user"]:
            self.client.username_pw_set(broker["user"], broker["password"])
        if broker["tls"]:
            self.client.tls_set(ca_certs=broker["ca_file"] or None)
        self.client.will_set(self.availability, "offline", qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.max_queued_messages_set(10)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish
        self.client.on_connect_fail = lambda client, userdata: LOG.warning("MQTT connection failed; retrying.")
        self.worker = threading.Thread(target=self.send_loop, name="mqtt-outbox", daemon=True)

    def announce(self):
        topic, payload = discovery(self.config)
        self.client.publish(topic, json.dumps(payload), qos=1, retain=True)
        self.publish_availability()

    def publish_availability(self):
        if self.connected.is_set():
            return self.client.publish(self.availability,
                "online" if self.device_connected.is_set() else "offline", qos=1, retain=True)
        return None

    def set_device(self, online):
        if online:
            self.device_connected.set()
        else:
            self.device_connected.clear()
        self.publish_availability()

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            LOG.warning("MQTT refused the connection (%s).", reason_code)
            return
        self.connected.set()
        client.subscribe(self.config["mqtt"]["discovery_prefix"].rstrip("/") + "/status", qos=1)
        self.announce()
        LOG.info("MQTT connected; discovery announced.")

    def on_disconnect(self, client, userdata, *args):
        self.connected.clear()
        if not self.stop.is_set():
            LOG.warning("MQTT disconnected; unsent scans stay in the outbox.")

    def on_message(self, client, userdata, message):
        if message.payload == b"online":
            # Re-announce config after HA starts, never replay an old sensor state.
            self.announce()

    def on_publish(self, client, userdata, mid, *args):
        with self.publish_lock:
            if mid == self.pending_mid:
                if args and getattr(args[0], "is_failure", False):
                    LOG.error("Broker rejected a scan; it remains in the outbox.")
                    return
                self.pending_ack.set()

    def start(self):
        broker = self.config["mqtt"]
        self.client.connect_async(broker["host"], broker["port"], keepalive=30)
        self.client.loop_start()
        self.worker.start()

    def send_loop(self):
        pending = None
        while not self.stop.is_set():
            if not self.connected.wait(0.5):
                continue
            if (not self.config.get("scan_send_enabled", True) or self.test_paused.is_set()) and pending is None:
                self.stop.wait(0.1)
                continue
            row = self.outbox.first()
            if row is None:
                self.stop.wait(0.1)
                continue
            try:
                if pending is None:
                    # Register the MID under the callback lock: an immediate PUBACK
                    # must not arrive before we know which scan it acknowledges.
                    with self.scan_gate:
                        if self.test_paused.is_set() or not self.config.get("scan_send_enabled", True):
                            continue
                        with self.publish_lock:
                            self.pending_ack.clear()
                            info = self.client.publish(row[1], row[2], qos=1, retain=False)
                            self.pending_mid = info.mid if info.rc in (0, 4) else None
                    if self.pending_mid is None:
                        self.stop.wait(1)
                        continue
                    pending = row[0]
                if self.pending_ack.wait(timeout=1):
                    self.outbox.remove(pending)
                    LOG.info("Scan delivered (ID %s).", json.loads(row[2])["scan_id"])
                    pending = None
            except (RuntimeError, OSError):
                self.stop.wait(1)
            except sqlite3.Error:
                LOG.exception("Outbox error; stopping transmission to preserve queued scans.")
                self.stop.set()

    def close(self):
        self.stop.set()
        if self.worker.is_alive():
            self.worker.join(timeout=5)
        self.device_connected.clear()
        info = self.publish_availability()
        if info is not None:
            try:
                info.wait_for_publish(timeout=2)
            except RuntimeError:
                pass
        self.client.disconnect()
        self.client.loop_stop()


async def read_device(config, consume, set_device, stop, observe=None):
    from evdev import InputDevice, ecodes
    scanner = config["scanner"]
    waiting = False
    while not stop.is_set():
        device = None
        try:
            device = InputDevice(scanner["device"])
            device.grab()
            set_device(True)
            waiting = False
            LOG.info("Scanner connected: %s (%s layout).", device.name, scanner["layout"])
            decoder = Decoder(scanner["layout"], output_profile=scanner.get("output_profile", "standard"))
            was_test = False
            test_partial = False
            test_last = None
            async for event in device.async_read_loop():
                if stop.is_set():
                    break
                if event.type == ecodes.EV_KEY:
                    test_event = observe(event.code, event.value) if observe is not None else False
                    is_test = bool(test_event)
                    if is_test != was_test:
                        decoder = Decoder(scanner["layout"], output_profile=scanner.get("output_profile", "standard"))
                        if is_test:
                            test_partial = False
                        if was_test and test_partial:
                            # Do not forward the tail of a test interrupted by its
                            # timer/abort. Discard through the next terminator or gap.
                            decoder.invalid = True
                            decoder.last = test_last
                            decoder.profile_last = test_last
                    was_test = is_test
                    if is_test:
                        test_last = time.monotonic()
                        if test_event == 'complete':
                            test_partial = False
                        elif event.value == 1 and event.code != 69:
                            test_partial = event.code not in (28, 96, 15)
                        continue
                    text = decoder.feed(event.code, event.value)
                    if text is not None:
                        consume(text)
        except OSError as error:
            if not waiting:
                LOG.warning("Waiting for scanner (%s). Check device path and permissions.", error.strerror)
                waiting = True
        finally:
            set_device(False)
            if device is not None:
                device.close()
        await asyncio.sleep(2)


async def run(config, state_directory, config_path=None):
    from . import config as settings
    while True:
        reload = await run_once(config, state_directory, config_path)
        if not reload:
            return
        config = settings.load(config_path)


async def run_once(config, state_directory, config_path):
    import signal
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    outbox = Outbox(Path(state_directory) / "outbox.sqlite3")
    publisher = None
    task = None
    server = None
    dashboard = None
    reload_requested = threading.Event()
    try:
        publisher = Publisher(config, outbox)
        publisher.start()

        from .web import Dashboard
        dashboard = Dashboard(config, config_path, publisher, outbox,
                              lambda: (reload_requested.set(), loop.call_soon_threadsafe(stop.set)))
        if config.get("web", {}).get("enabled"):
            try:
                server = dashboard.start()
            except OSError:
                LOG.error("Web interface could not start. Check bind address/port; receiver continues.")

        def consume(text):
            dashboard.scan(text)
            if not config.get("scan_send_enabled", True):
                return
            payload = scan_payload(text, config["scanner"]["id"])
            outbox.put(config["scanner"]["topic"], payload)
            LOG.info("Scan queued (ID %s, %s characters).", payload["scan_id"], len(text))

        task = asyncio.create_task(read_device(config, consume, publisher.set_device, stop, dashboard.observe))
        waiter = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait((task, waiter), return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                await task
        finally:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if dashboard is not None:
            dashboard.end_test()
        if server is not None:
            server.shutdown()
            server.server_close()
        if publisher is not None:
            publisher.close()
        outbox.close()
    return reload_requested.is_set()
