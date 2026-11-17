import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from usb_scanner_mqtt import config
from usb_scanner_mqtt.cli import main
from usb_scanner_mqtt.keyboard import Decoder
from usb_scanner_mqtt.receiver import Outbox, discovery, scan_payload, Publisher


def example():
    value = config.defaults()
    value["mqtt"]["host"] = "127.0.0.1"
    value["scanner"]["device"] = "/dev/input/by-id/test-event-kbd"
    return value


class DecoderTests(unittest.TestCase):
    def test_identical_physical_scans_are_both_returned(self):
        decoder = Decoder()
        results = []
        for _ in range(2):
            for code in (2,11,11,28):
                results.append(decoder.feed(code, 1))
                self.assertIsNone(decoder.feed(code, 0))
        self.assertEqual([r for r in results if r is not None], ["100", "100"])

    def test_shift_url_and_german_umlauts(self):
        decoder = Decoder()
        decoder.feed(42,1)
        decoder.feed(39,1)
        decoder.feed(42,0)
        decoder.feed(53,1)
        self.assertEqual(decoder.feed(28,1), ":/")
        decoder = Decoder("de")
        decoder.feed(40,1)
        decoder.feed(42,1)
        decoder.feed(26,1)
        decoder.feed(42,0)
        decoder.feed(100,1)
        decoder.feed(16,1)
        decoder.feed(100,0)
        self.assertEqual(decoder.feed(28,1), "äÜ@")

    def test_repeats_releases_empty_ignored(self):
        decoder = Decoder()
        decoder.feed(2,1)
        decoder.feed(2,2)
        decoder.feed(2,0)
        self.assertEqual(decoder.feed(15,1), "1")
        self.assertIsNone(decoder.feed(28,1))

    def test_partial_scan_expires(self):
        decoder = Decoder()
        decoder.feed(2,1,now=1)
        decoder.feed(3,1,now=4)
        self.assertEqual(decoder.feed(28,1,now=4.1), "2")

    def test_unsupported_and_oversized_scan_rejected(self):
        for codes in ((2,59,28), (2,2,2,28), (29,2,28)):
            decoder = Decoder(max_length=2)
            self.assertTrue(all(decoder.feed(code,1) is None for code in codes))

    def test_caps_backspace_keypad(self):
        decoder = Decoder()
        decoder.feed(58,1)
        decoder.feed(30,1)
        decoder.feed(14,1)
        decoder.feed(48,1)
        decoder.feed(79,1)
        self.assertEqual(decoder.feed(96,1), "B1")


class ConfigTests(unittest.TestCase):
    def test_atomic_save_permissions_and_credentials_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            value = example()
            value["mqtt"]["password"] = "private-password"
            config.save(value, path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config.load(path), value)
            config.save(value,path)
            self.assertEqual(len(list(Path(directory).iterdir())),1)

    def test_bad_config_does_not_replace_good_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            value = example()
            config.save(value,path)
            value["scanner"]["topic"] = "scans/#"
            with self.assertRaises(ValueError):
                config.save(value,path)
            self.assertEqual(config.load(path)["scanner"]["topic"], "usb-scanner-mqtt/usb-scanner-1/scan")

    def test_malformed_configuration_shapes(self):
        for value in ([], None, "invalid"):
            with self.subTest(root=value), self.assertRaises(ValueError):
                config.validate(value)
        for section in ("web", "mqtt", "scanner"):
            conf = example()
            conf[section] = []
            with self.subTest(section=section), self.assertRaises(ValueError):
                config.validate(conf)
        conf = example()
        conf["scanner"]["id"] = 123
        with self.assertRaises(ValueError):
            config.validate(conf)

    def test_bad_fields(self):
        for section, key, value in (("mqtt","port",True), ("mqtt","port",0),
                ("scanner","layout","xx"), ("scanner","device","/etc/passwd"),
                ("scanner","id","bad/id"), ("mqtt","tls","false")):
            conf = example()
            conf[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                config.validate(conf)

    def test_cli_set_retains_password_and_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            value = example()
            value["mqtt"]["password"] = "do-not-print"
            config.save(value,path)
            output = io.StringIO()
            with patch("usb_scanner_mqtt.cli.os.geteuid",return_value=0), \
                    patch("usb_scanner_mqtt.cli.restart_if_running") as restart, contextlib.redirect_stdout(output):
                self.assertEqual(main(["--config",str(path),"set","layout","de"]),0)
            self.assertEqual(config.load(path)["mqtt"]["password"], "do-not-print")
            self.assertEqual(config.load(path)["scanner"]["layout"], "de")
            self.assertNotIn("do-not-print",output.getvalue())
            restart.assert_called_once()


class OutboxTests(unittest.TestCase):
    def test_publish_ack_only_matches_pending_scan(self):
        import threading
        publisher = Publisher.__new__(Publisher)
        publisher.control_lock = threading.Lock(); publisher.pending_controls = {}
        publisher.publish_lock = threading.Lock()
        publisher.registering_publish = False
        publisher.early_acks = {}
        publisher.pending_mid = 42
        publisher.pending_ack = threading.Event()
        publisher.on_publish(None,None,41)
        self.assertFalse(publisher.pending_ack.is_set())
        publisher.on_publish(None,None,42)
        self.assertTrue(publisher.pending_ack.is_set())

    def test_immediate_ack_does_not_deadlock_or_match_discovery(self):
        import threading
        from types import SimpleNamespace
        from unittest.mock import Mock
        publisher = Publisher.__new__(Publisher)
        publisher.control_lock = threading.Lock(); publisher.pending_controls = {}
        publisher.publish_lock=threading.Lock();publisher.pending_ack=threading.Event()
        publisher.pending_mid=None;publisher.registering_publish=False;publisher.early_acks={}
        publisher.client=Mock()
        def immediate(*args,**kwargs):
            # If the caller holds the callback lock, this is the old deadlock.
            self.assertTrue(publisher.publish_lock.acquire(blocking=False))
            publisher.publish_lock.release()
            publisher.on_publish(None,None,7)  # unrelated discovery ACK
            publisher.on_publish(None,None,42)
            return SimpleNamespace(mid=42,rc=0)
        publisher.client.publish.side_effect=immediate
        self.assertEqual(publisher.publish_scan('scan','{}'),42)
        self.assertTrue(publisher.pending_ack.is_set());self.assertEqual(publisher.early_acks,{})
        def reject(*args,**kwargs):
            publisher.on_publish(None,None,43,SimpleNamespace(is_failure=True))
            return SimpleNamespace(mid=43,rc=0)
        publisher.client.publish.side_effect=reject
        with self.assertLogs('usb_scanner_mqtt.receiver',level='ERROR'):
            publisher.publish_scan('scan','{}')
        self.assertFalse(publisher.pending_ack.is_set())

    def test_persistent_fifo_ids_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.db"
            first, second = scan_payload("00123","kitchen"), scan_payload("00123","kitchen")
            self.assertNotEqual(first["scan_id"],second["scan_id"])
            outbox = Outbox(path)
            try:
                outbox.put("topic1",first)
                outbox.put("topic2",second)
                sequence = outbox.first()[0]
            finally:
                outbox.close()
            outbox = Outbox(path)
            try:
                self.assertEqual(json.loads(outbox.first()[2]),first)
                outbox.remove(sequence)
                self.assertEqual(outbox.first()[1],"topic2")
                self.assertEqual(json.loads(outbox.first()[2]),second)
                outbox.remove(outbox.first()[0])
                self.assertIsNone(outbox.first())
                self.assertEqual(path.stat().st_mode & 0o777,0o600)
            finally:
                outbox.close()

    def test_bounded_queue_keeps_existing_scans(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = Outbox(Path(directory)/"queue.db")
            try:
                for _ in range(1000):
                    outbox.put("scan",scan_payload("123","s"))
                first = outbox.first()
                with self.assertRaises(RuntimeError):
                    outbox.put("scan",scan_payload("456","s"))
                self.assertEqual(outbox.first(),first)
            finally:
                outbox.close()

    def test_discovery_uses_stable_identity_and_scan_attributes(self):
        conf = example()
        topic, payload = discovery(conf)
        self.assertEqual(discovery(conf),(topic,payload))
        self.assertTrue(topic.startswith("homeassistant/sensor/"))
        self.assertEqual(payload["state_topic"], conf["scanner"]["topic"])
        self.assertIn("scan_id",payload["json_attributes_template"])
        self.assertIn("255",payload["value_template"])
        conf["scanner"]["name"] = "Renamed"
        self.assertEqual(discovery(conf)[1]["unique_id"], payload["unique_id"])

class PublisherReadFailureTests(unittest.TestCase):
    def test_outbox_read_error_stops_transmission_cleanly(self):
        import sqlite3
        import threading
        from unittest.mock import Mock
        from usb_scanner_mqtt.receiver import Publisher
        publisher = Publisher.__new__(Publisher)
        publisher.control_lock = threading.Lock(); publisher.pending_controls = {}
        publisher.stop = threading.Event()
        publisher.connected = threading.Event(); publisher.connected.set()
        publisher.test_paused = threading.Event()
        publisher.config = {'scan_send_enabled': True}
        publisher.outbox = Mock(); publisher.outbox.first.side_effect = sqlite3.OperationalError('test read failure')
        with self.assertLogs('usb_scanner_mqtt.receiver', level='ERROR'):
            publisher.send_loop()
        self.assertTrue(publisher.stop.is_set())
        publisher.outbox.remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
