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
            exercise_controls(port)
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
            assert dashboard.snapshot()['test']['layouts'] == {'us': 'y', 'de': 'z', 'gb': 'y', 'fr': 'y', 'es': 'y'}
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
            # Product enrichment uses one real MQTT message per scan; HTTP is a fixture.
            from usb_scanner_mqtt.open_facts import Enricher
            from unittest.mock import Mock
            options=dict(enabled=True,include_mqtt=True,language='de',timeout=1)
            product=dict(name='Test product',brand='Test',package_quantity='1 l',image_url=None,product_type='food',source='Open Food Facts')
            publisher.test_paused.set()
            enriched=scan_payload('0012345',conf['scanner']['id'])
            outbox.put(conf['scanner']['topic'],enriched,options,record=True)
            assert outbox.first() is None and outbox.count()==1
            worker=Enricher(outbox,Mock(lookup=Mock(return_value=('found',product,False))))
            assert worker.process()
            outbox.clear_history()  # Clearing display entries must not discard pending sends.
            publisher.test_paused.clear()
            wait(lambda:outbox.count()==0,'enriched scan not acknowledged')
            wait(lambda:any(t==conf['scanner']['topic'] and json.loads(p)['scan_id']==enriched['scan_id'] for t,p,_ in messages),'enriched scan missing')
            delivered=[(json.loads(p),retained) for t,p,retained in messages if t==conf['scanner']['topic'] and json.loads(p)['scan_id']==enriched['scan_id']]
            assert len(delivered)==1 and not delivered[0][1]
            assert delivered[0][0]['off_data']==product and delivered[0][0]['ean']=='0012345'
            timeout_scan=scan_payload('0099999',conf['scanner']['id'])
            outbox.put(conf['scanner']['topic'],timeout_scan,options,record=True)
            worker.lookup.lookup.return_value=('timeout',None,False)
            assert worker.process()
            wait(lambda:outbox.count()==0,'timeout scan not delivered')
            wait(lambda:any(t==conf['scanner']['topic'] and json.loads(p)['scan_id']==timeout_scan['scan_id'] for t,p,_ in messages),'timeout message missing')
            assert outbox.history()[0]['status']=='sent'
            timeout_messages=[json.loads(p) for t,p,_ in messages if t==conf['scanner']['topic'] and json.loads(p)['scan_id']==timeout_scan['scan_id']]
            assert len(timeout_messages)==1 and timeout_messages[0]['off_status']=='timeout' and timeout_messages[0]['off_data'] is None
            print('PASS: MQTT discovery, equal scans, leading zero, stable replay ID, HA birth, non-retained scans, paused queue/restart/resume, automatic test pause/resume, packed Alt profile, exact language samples, multi-scan pause/resume, offline availability, durable history and same-message product enrichment / timeout')
        finally:
            if publisher:
                publisher.close()
            outbox.close()
            observer.disconnect()
            observer.loop_stop()


def exercise_controls(port):
    from usb_scanner_mqtt import config as settings, mqtt_controls as controls
    import sys
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'config.json'
        conf=defaults();conf['mqtt'].update(host='127.0.0.1',port=port)
        conf['scanner'].update(id='controls-test',device='/dev/input/test')
        conf['scanner']['topic']=controls.base_topic(conf)+'/scan'
        settings.save(conf,path)
        messages=[]
        observer=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,protocol=mqtt.MQTTv5)
        observer.on_message=lambda c,u,m:messages.append((m.topic,bytes(m.payload),m.retain))
        observer.connect('127.0.0.1',port);observer.subscribe('#',qos=1);observer.loop_start()
        outbox=Outbox(Path(directory)/'outbox.db')
        publisher=None
        def start(config):
            pub=Publisher(config,outbox)
            dash=Dashboard(config,path,pub,outbox,lambda:None)
            pub.control=dash.set_control;pub.start()
            wait(pub.connected.is_set,'controls publisher not connected')
            return pub,dash
        def latest(topic):
            return next((payload for t,payload,_ in reversed(messages) if t==topic),None)
        def send(key,value,retain=False):
            observer.publish(controls.control_topic(conf,key,'set'),value,qos=1,retain=retain).wait_for_publish(3)
        try:
            publisher,dashboard=start(conf)
            sensor_topic,sensor_config=discovery(conf)
            discovery_topics={sensor_topic,*[topic for topic,_ in controls.discovery(conf)]}
            wait(lambda:all(latest(topic) for topic in discovery_topics),'missing sensor/switch discovery')
            wait(lambda:latest(publisher.service_availability)==b'online','switches unavailable without USB')
            wait(lambda:latest(publisher.availability)==b'offline','missing USB must mark sensor unavailable')
            for key in controls.CONTROLS:
                send(key,'ON');wait(lambda:controls.values(settings.load(path))[key],'ON command not persisted')
                wait(lambda:latest(controls.control_topic(conf,key,'state'))==b'ON','ON state not confirmed')
                send(key,'OFF');wait(lambda:not controls.values(settings.load(path))[key],'OFF command not persisted')
                wait(lambda:latest(controls.control_topic(conf,key,'state'))==b'OFF','OFF state not confirmed')
            # A live retained command is ignored too (retainAsPublished is enabled).
            send('open_facts','ON',retain=True);time.sleep(.3)
            assert not settings.load(path)['open_facts']['enabled']
            count=sum(t==sensor_topic for t,_,_ in messages)
            observer.publish('homeassistant/status','online',qos=1).wait_for_publish(3)
            wait(lambda:sum(t==sensor_topic for t,_,_ in messages)>count,'HA birth did not rediscover controls')
            for key in controls.CONTROLS:assert latest(controls.control_topic(conf,key,'state'))==b'OFF'
            # A newly connected HA observer receives discovery/states, not stale scan data.
            retained=[];fresh=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,protocol=mqtt.MQTTv5)
            fresh.on_message=lambda c,u,m:retained.append((m.topic,bytes(m.payload),m.retain))
            fresh.connect('127.0.0.1',port);fresh.subscribe('#',qos=1);fresh.loop_start()
            try:
                wait(lambda:all(any(t==topic and flag for t,_,flag in retained) for topic in discovery_topics),'switch discovery not retained')
                wait(lambda:all(any(t==controls.control_topic(conf,key,'state') and payload==b'OFF' and flag for t,payload,flag in retained) for key in controls.CONTROLS),'switch states not retained')
                assert not any(t==conf['scanner']['topic'] for t,_,_ in retained)
            finally:fresh.disconnect();fresh.loop_stop()
            # GUI changes are announced after the same receiver reload used by the application.
            dashboard.save({'scanner':{'name':'Renamed from GUI'},'open_facts':{'include_mqtt':True}})
            publisher.close();publisher=None
            conf=settings.load(path);publisher,dashboard=start(conf)
            wait(lambda:latest(controls.control_topic(conf,'product_data','state'))==b'ON','GUI save not reflected in HA')
            assert not conf['open_facts']['enabled']  # Stale retained ON not replayed on subscribe.
            time.sleep(.3);assert not settings.load(path)['open_facts']['enabled']
            # New machine/fresh settings, same scanner ID: same four identities/topics.
            publisher.close();publisher=None
            replacement=defaults();replacement['mqtt'].update(host='127.0.0.1',port=port)
            replacement['scanner'].update(id=conf['scanner']['id'],name='New machine',device='/dev/input/test',topic=conf['scanner']['topic'])
            settings.save(replacement,path);conf=replacement
            publisher,dashboard=start(conf)
            wait(lambda:latest(sensor_topic) and json.loads(latest(sensor_topic))['device']['name']=='New machine','fresh install did not reuse discovery topic')
            assert discovery(conf)[1]['unique_id']==sensor_config['unique_id']
            assert {discovery(conf)[0],*[topic for topic,_ in controls.discovery(conf)]}==discovery_topics
            assert all(json.loads(latest(topic))['device']['identifiers']==sensor_config['device']['identifiers'] for topic in discovery_topics)
            send('open_facts','ON');wait(lambda:settings.load(path)['open_facts']['enabled'],'new live command failed after replacement')
            publisher.close();publisher=None
            wait(lambda:latest(controls.base_topic(conf)+'/status/availability')==b'offline','clean shutdown did not mark service offline')
            # Abrupt process termination exercises the actual MQTT Last Will.
            crashed=defaults();crashed['mqtt'].update(host='127.0.0.1',port=port)
            crashed['scanner'].update(id='will-test',device='/dev/input/test')
            crash_path=Path(directory)/'crash.json';settings.save(crashed,crash_path)
            code="import sys,time;from pathlib import Path;from usb_scanner_mqtt.config import load;from usb_scanner_mqtt.receiver import Publisher,Outbox;p=Publisher(load(sys.argv[1]),Outbox(Path(sys.argv[2])));p.start();p.set_device(True);time.sleep(30)"
            child=subprocess.Popen([sys.executable,'-c',code,str(crash_path),str(Path(directory)/'crash.db')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                will_topic=controls.base_topic(crashed)+'/status/availability'
                wait(lambda:latest(will_topic)==b'online','crash-test service not online')
                child.terminate();child.wait(timeout=5)
                wait(lambda:latest(will_topic)==b'offline','Last Will did not mark crashed service offline')
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)
            print('PASS: three real MQTT switches, persisted ON/OFF, retained state/discovery, HA birth, GUI reload, stale retained command rejection, stable identity on new machine/name, controls without USB, graceful offline and crash Last Will')
        finally:
            if publisher:publisher.close()
            outbox.close();observer.disconnect();observer.loop_stop()


if __name__ == '__main__':
    main()
