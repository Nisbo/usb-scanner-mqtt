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
from usb_scanner_mqtt.web import Dashboard
from usb_scanner_mqtt.keyboard import Decoder
from usb_scanner_mqtt.calibration import LANGUAGES
from test_calibration import packed_input
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
            # A temporary test pauses only scan transmission; MQTT/birth stay live.
            dashboard = Dashboard(conf, None, publisher, outbox, lambda: None)
            dashboard.begin_test()
            waiting = scan_payload('queued-before-test', conf['scanner']['id'])
            outbox.put(conf['scanner']['topic'], waiting)
            time.sleep(0.3)
            assert outbox.first() is not None
            assert not any(t == conf['scanner']['topic'] and json.loads(p)['scan_id'] == waiting['scan_id'] for t,p,_ in messages)
            assert publisher.connected.is_set()
            count = len([1 for t,_,_ in messages if t == dt])
            observer.publish('homeassistant/status','online',qos=1).wait_for_publish(2)
            wait(lambda:len([1 for t,_,_ in messages if t == dt]) > count, 'temporary test disconnected MQTT')
            for code, value in ((21,1), (21,0), (28,1)):
                assert dashboard.observe(code, value)
            wait(lambda:outbox.first() is None, 'test completion failed to resume queue')
            assert dashboard.snapshot()['test']['layouts'] == {'us': 'y', 'de': 'z'}
            assert conf['scan_send_enabled']
            dashboard.end_test()
            # A multi-scan session keeps MQTT live and never queues its local scans.
            monitor=Dashboard(conf,None,publisher,outbox,lambda:None)
            monitor.begin_scanning()
            paused_payload=scan_payload('already-waiting',conf['scanner']['id'])
            outbox.put(conf['scanner']['topic'],paused_payload)
            for _ in range(2):
                for code,value in ((11,1),(11,0),(2,1),(2,0),(28,1),(28,0)):
                    assert monitor.observe(code,value)
            assert [entry['text'] for entry in monitor.snapshot()['scan_items']] == ['01','01']
            time.sleep(0.3)
            assert publisher.connected.is_set()
            assert json.loads(outbox.first()[2])['scan_id'] == paused_payload['scan_id']
            assert not any(t == conf['scanner']['topic'] and json.loads(p)['ean'] == '01' for t,p,_ in messages)
            monitor.stop_scanning()
            wait(lambda:outbox.first() is None,'monitor stop did not restore queued transmission')
            monitor.end_test()
            # Pending scan survives process restart and keeps its ID.
            publisher.close()
            publisher = None
            payload=scan_payload('0012345678905',conf['scanner']['id'])
            outbox.put(conf['scanner']['topic'],payload)
            outbox.close()
            outbox=Outbox(Path(directory)/'outbox.db')
            # Persisted scans remain queued through a paused publisher restart.
            conf['scan_send_enabled'] = False
            publisher=Publisher(conf,outbox)
            publisher.start()
            wait(publisher.connected.is_set, 'paused publisher failed to connect')
            time.sleep(0.3)
            assert json.loads(outbox.first()[2])['scan_id'] == payload['scan_id']
            assert not any(t == conf['scanner']['topic'] and json.loads(p)['scan_id'] == payload['scan_id'] for t,p,_ in messages)
            count = len([1 for t,_,_ in messages if t == dt])
            observer.publish('homeassistant/status', 'online', qos=1).wait_for_publish(2)
            wait(lambda:len([1 for t,_,_ in messages if t == dt]) > count, 'paused discovery failed')
            publisher.close()
            conf['scan_send_enabled'] = True
            publisher=Publisher(conf,outbox)
            publisher.start()
            wait(lambda:outbox.first() is None,'restart failed to drain persisted scan')
            wait(lambda:any(t == conf['scanner']['topic'] and json.loads(p)['scan_id'] == payload['scan_id'] for t,p,_ in messages),'persisted ID changed')
            # Missing device reports offline without terminating MQTT.
            wait(lambda:any(t.endswith('/availability') and p == b'offline' for t,p,_ in messages),'missing scanner not offline')
            # Synthetic profile input crosses the real broker; no hardware is implied.
            keypad=dict(zip('0123456789',(82,79,80,81,75,76,77,71,72,73)))
            ids=[]
            for number, expected in ((50189,'Ä'),(50189,'Ä'),(50241,'ÄA')):
                decoder=Decoder(output_profile='alt-pair-latin1')
                events=[(56,1)]
                for digit in str(number): events += [(keypad[digit],1),(keypad[digit],0)]
                events += [(56,0),(28,1)]
                decoded=[]
                for code,value in events:
                    text=decoder.feed(code,value)
                    if text is not None: decoded.append(text)
                assert decoded == [expected]
                payload=scan_payload(decoded[0],conf['scanner']['id'])
                ids.append(payload['scan_id'])
                outbox.put(conf['scanner']['topic'],payload)
            wait(lambda:outbox.first() is None,'profile scans not acknowledged')
            wait(lambda:len([1 for t,p,_ in messages if t == conf['scanner']['topic'] and json.loads(p)['scan_id'] in ids]) == 3,'profile messages missing')
            profile_scans=[(json.loads(p),retained) for t,p,retained in messages if t == conf['scanner']['topic'] and json.loads(p)['scan_id'] in ids]
            assert [payload['ean'] for payload,_ in profile_scans] == ['Ä','Ä','ÄA']
            assert len(set(ids)) == 3
            assert not any(retained for _,retained in profile_scans)
            # Every language sample crosses the real local broker without text changes.
            language_ids={}
            for language,sample in LANGUAGES.items():
                decoder=Decoder(output_profile='alt-pair-latin1')
                decoded=[]
                for code,value in packed_input(sample['text']):
                    text=decoder.feed(code,value)
                    if text is not None:decoded.append(text)
                assert decoded == [sample['text']]
                payload=scan_payload(decoded[0],conf['scanner']['id'])
                language_ids[payload['scan_id']]=sample['text']
                outbox.put(conf['scanner']['topic'],payload)
            wait(lambda:outbox.first() is None,'language scans not acknowledged')
            wait(lambda:len([1 for t,p,_ in messages if t == conf['scanner']['topic'] and json.loads(p)['scan_id'] in language_ids]) == len(language_ids),'language messages missing')
            for topic,payload,retained in messages:
                if topic != conf['scanner']['topic']:continue
                scan=json.loads(payload)
                if scan['scan_id'] in language_ids:
                    assert scan['ean'] == language_ids[scan['scan_id']]
                    assert not retained
            print('PASS: MQTT discovery, equal scans, leading zero, stable replay ID, HA birth, non-retained scans, paused queue/restart/resume, automatic test pause/resume, packed Alt profile, exact language samples, multi-scan pause/resume, offline availability')
        finally:
            if publisher:
                publisher.close()
            outbox.close()
            observer.disconnect()
            observer.loop_stop()


if __name__ == '__main__':
    main()
