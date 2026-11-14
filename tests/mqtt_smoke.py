"""Integration smoke test against Mosquitto (test dependency, not installed by the receiver)."""
import json
import socket
import tempfile
import time
from pathlib import Path

import os
import subprocess
import paho.mqtt.client as mqtt
from usb_scanner_mqtt.config import defaults
from usb_scanner_mqtt.receiver import Publisher, Outbox, scan_payload, discovery


def wait(predicate, message, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory() as directory:
        configuration = Path(directory) / 'mosquitto.conf'
        configuration.write_text(f'listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n')
        broker = subprocess.Popen([os.environ.get('MOSQUITTO_BINARY','mosquitto'), '-c', str(configuration)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            def ready():
                if broker.poll() is not None:
                    raise AssertionError('broker failed to start')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                        return True
                except OSError:
                    return False
            wait(ready, 'broker did not become ready', timeout=30)
            exercise(port)
        finally:
            broker.terminate()
            broker.wait(timeout=5)


def exercise(port):
    conf = defaults()
    conf['mqtt'].update(host='127.0.0.1',port=port)
    conf['scanner']['device'] = '/dev/input/test'
    messages = []
    def client():
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    observer = client()
    observer.on_message = lambda client, userdata, msg: messages.append((msg.topic, bytes(msg.payload), msg.retain))
    observer.connect('127.0.0.1', port)
    observer.subscribe('#',qos=1)
    observer.loop_start()
    with tempfile.TemporaryDirectory() as directory:
        outbox = Outbox(Path(directory)/'outbox.db')
        publisher = Publisher(conf,outbox)
        try:
            publisher.start()
            wait(publisher.connected.is_set,'publisher failed to connect')
            publisher.set_device(True)
            dt, _ = discovery(conf)
            wait(lambda:any(t == dt for t,_,_ in messages),'no discovery')
            for _ in range(2):
                outbox.put(conf['scanner']['topic'],scan_payload('0012345678905',conf['scanner']['id']))
            wait(lambda:len([1 for t,_,_ in messages if t == conf['scanner']['topic']]) == 2,'two scans missing')
            wait(lambda:outbox.first() is None,'outbox not acknowledged')
            scans = [json.loads(p) for t,p,_ in messages if t == conf['scanner']['topic']]
            assert scans[0]['scan_id'] != scans[1]['scan_id']
            assert all(s['ean'] == '0012345678905' for s in scans)
            # HA restart sends birth: rediscover, never send scans again.
            count = len([1 for t,_,_ in messages if t == dt])
            observer.publish('homeassistant/status','online',qos=1).wait_for_publish(2)
            wait(lambda:len([1 for t,_,_ in messages if t == dt]) > count,'birth did not rediscover')
            time.sleep(0.3)
            assert len([1 for t,_,_ in messages if t == conf['scanner']['topic']]) == 2
            # New subscriber receives discovery/availability, but NO retained scan.
            retained=[]
            fresh=client()
            fresh.on_message=lambda client, userdata, msg:retained.append((msg.topic,msg.payload))
            fresh.connect('127.0.0.1',port)
            fresh.subscribe('#',qos=1)
            fresh.loop_start()
            try:
                wait(lambda:any(t == dt for t,_ in retained),'discovery is not retained')
                time.sleep(0.3)
                assert not any(t == conf['scanner']['topic'] for t,_ in retained)
            finally:
                fresh.disconnect()
                fresh.loop_stop()
            # Pending scan survives process restart and keeps its ID.
            publisher.close()
            publisher = None
            payload=scan_payload('0012345678905',conf['scanner']['id'])
            outbox.put(conf['scanner']['topic'],payload)
            outbox.close()
            outbox=Outbox(Path(directory)/'outbox.db')
            publisher=Publisher(conf,outbox)
            publisher.start()
            wait(lambda:outbox.first() is None,'restart failed to drain persisted scan')
            wait(lambda:any(t == conf['scanner']['topic'] and json.loads(p)['scan_id'] == payload['scan_id'] for t,p,_ in messages),'persisted ID changed')
            # Missing device reports offline without terminating MQTT.
            wait(lambda:any(t.endswith('/availability') and p == b'offline' for t,p,_ in messages),'missing scanner not offline')
            print('PASS: MQTT discovery, equal scans, leading zero, stable replay ID, HA birth, non-retained scans, offline availability')
        finally:
            if publisher:
                publisher.close()
            outbox.close()
            observer.disconnect()
            observer.loop_stop()


if __name__ == '__main__':
    main()
