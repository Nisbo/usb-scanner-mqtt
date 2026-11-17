import asyncio
import copy
import http.client
import json
import sys
from types import SimpleNamespace
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, AsyncMock, patch

from usb_scanner_mqtt import config
from usb_scanner_mqtt.cli import main
from usb_scanner_mqtt.receiver import Outbox, Publisher, scan_payload, run_once, read_device
from usb_scanner_mqtt.web import Dashboard


class WebTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'config.json'
        self.config = config.defaults()
        self.config['mqtt'].update(host='127.0.0.1', password='SECRET')
        self.config['scanner']['device'] = '/dev/input/test'
        self.config['scan_send_enabled'] = False
        config.save(self.config, self.path)
        self.outbox = Outbox(Path(self.directory.name) / 'outbox.db')
        self.addCleanup(self.outbox.close)
        self.publisher = Mock()
        self.publisher.scan_gate = threading.RLock()
        self.publisher.test_paused = threading.Event()
        self.publisher.connected = threading.Event()
        self.publisher.device_connected = threading.Event()
        self.reload = Mock()
        self.dashboard = Dashboard(self.config, self.path, self.publisher, self.outbox, self.reload)
        self.addCleanup(self.dashboard.end_test)

    def server(self):
        # Port 0 only for isolated tests; production config rejects it.
        self.config['web'].update(host='127.0.0.1', port=0)
        server = self.dashboard.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_port

    def request(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        client.request(method, path, json.dumps(body) if body is not None else None, headers or {})
        response = client.getresponse()
        result = response.status, response.read().decode()
        client.close()
        return result

    def test_http_secrets_origin_host_and_save(self):
        self.server()
        status, body = self.request('GET', '/api/config')
        self.assertEqual(status, 200)
        self.assertNotIn('SECRET', body)
        headers = {'X-CSRF-Token': json.loads(body)['token']}
        self.assertEqual(self.request('POST', '/api/config', {'scan_send_enabled': True})[0], 403)
        bad = {**headers, 'Origin': 'http://untrusted.example'}
        self.assertEqual(self.request('POST', '/api/config', {}, bad)[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'scanner.example'})[0], 200)
        self.assertEqual(self.request('GET', '/api/auth', headers={'Host': 'scanner.example','Sec-Fetch-Site':'cross-site'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'bad.example/path'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Host':'scanner.example','Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'})[0], 200)
        self.assertEqual(self.request('POST', '/api/config', {'scanner': {'layout': 'xx'}}, headers)[0], 400)
        self.assertEqual(config.load(self.path)['scanner']['layout'], 'us')
        patch = {'scanner': {'layout': 'de'}, 'mqtt': {'password': ''}}
        self.assertEqual(self.request('POST', '/api/config', patch, headers)[0], 200)
        self.assertEqual(config.load(self.path)['mqtt']['password'], 'SECRET')
        self.assertEqual(config.load(self.path)['scanner']['layout'], 'de')
        self.reload.assert_called_once()
        for path in ('/', '/app.js', '/style.css', '/qrcodegen.js', '/api/state', '/api/devices'):
            self.assertEqual(self.request('GET', path)[0], 200)

    def test_local_lookup_request_is_independent_and_validated(self):
        self.server()
        token = json.loads(self.request('GET','/api/auth')[1])['token']
        headers = {'X-CSRF-Token':token}
        self.assertEqual(self.request('POST','/api/scan/start',{'lookup':'true'},headers)[0],400)
        self.assertEqual(self.request('POST','/api/scan/start',{'lookup':True},headers)[0],200)
        self.assertTrue(self.dashboard.snapshot()['scan_lookup'])
        self.assertFalse(config.load(self.path)['open_facts']['enabled'])

    def test_capture_automatically_pauses_and_restores_without_changing_config(self):
        for enabled in (True, False):
            self.config['scan_send_enabled'] = enabled
            self.dashboard.begin_test()
            self.assertTrue(self.publisher.test_paused.is_set())
            self.assertFalse(self.dashboard.snapshot()['sending'])
            for code, value in ((21, 1), (21, 0), (28, 1)):
                self.assertTrue(self.dashboard.observe(code, value))
            result = self.dashboard.snapshot()['test']
            self.assertEqual(result['layouts'], {'us': 'y', 'de': 'z', 'gb': 'y', 'fr': 'y', 'es': 'y'})
            self.assertEqual(result['terminator'], 28)
            self.assertFalse(self.publisher.test_paused.is_set())
            self.assertFalse(self.dashboard.snapshot()['test_active'])
            self.assertEqual(self.dashboard.snapshot()['sending'], enabled)
            self.assertEqual(self.config['scan_send_enabled'], enabled)
            self.assertEqual(self.outbox.count(), 0)
            self.dashboard.result_until = time.monotonic() - 1
            self.dashboard.expire()
            self.assertIsNone(self.dashboard.result)
            self.assertEqual(self.dashboard.events, [])

    def test_abort_expiry_and_repeated_start(self):
        self.config['scan_send_enabled'] = True
        self.dashboard.begin_test()
        self.dashboard.observe(21, 1)
        self.dashboard.end_test()
        self.assertFalse(self.publisher.test_paused.is_set())
        self.assertIsNone(self.dashboard.snapshot()['test'])
        self.dashboard.begin_test()
        self.dashboard.expire()  # An older timer must not end a newly started test.
        self.assertTrue(self.dashboard.snapshot()['test_active'])
        self.dashboard.until = self.dashboard.result_until = time.monotonic() - 1
        self.dashboard.expire()
        self.assertFalse(self.publisher.test_paused.is_set())
        self.assertTrue(self.dashboard.snapshot()['sending'])
        self.assertEqual(self.dashboard.events, [])

    def test_testscan_is_excluded_from_normal_receiver_after_auto_resume(self):
        self.config['scan_send_enabled'] = True
        self.dashboard.begin_test()
        stop = asyncio.Event()
        class Device:
            name = 'Simulated scanner'
            def grab(self): pass
            def close(self): pass
            async def async_read_loop(self):
                for code, value in ((21,1),(21,0),(28,1),(28,0),(2,1),(2,0),(28,1)):
                    yield SimpleNamespace(type=1, code=code, value=value)
                stop.set()
        evdev = SimpleNamespace(InputDevice=lambda path: Device(), ecodes=SimpleNamespace(EV_KEY=1))
        received = []
        with patch.dict(sys.modules, evdev=evdev), patch('usb_scanner_mqtt.receiver.asyncio.sleep', new_callable=AsyncMock):
            asyncio.run(read_device(self.config, received.append, lambda value: None, stop, self.dashboard.observe))
        self.assertEqual(received, ['1'])
        self.assertEqual(self.dashboard.snapshot()['test']['layouts']['us'], 'y')
        self.assertFalse(self.publisher.test_paused.is_set())

    def test_aborted_partial_test_cannot_send_suffix_as_real_scan(self):
        self.config['scan_send_enabled'] = True
        self.dashboard.begin_test()
        dashboard = self.dashboard
        stop = asyncio.Event()
        class Device:
            name = 'Simulated scanner'
            def grab(self): pass
            def close(self): pass
            async def async_read_loop(self):
                yield SimpleNamespace(type=1, code=21, value=1)
                dashboard.end_test()
                for code in (2, 28, 3, 28):
                    yield SimpleNamespace(type=1, code=code, value=1)
                stop.set()
        evdev = SimpleNamespace(InputDevice=lambda path: Device(), ecodes=SimpleNamespace(EV_KEY=1))
        received = []
        with patch.dict(sys.modules, evdev=evdev), patch('usb_scanner_mqtt.receiver.asyncio.sleep', new_callable=AsyncMock):
            asyncio.run(read_device(self.config, received.append, lambda value: None, stop, dashboard.observe))
        self.assertEqual(received, ['2'])

    def test_profile_capture_finishes_on_embedded_cr_and_next_scan_is_not_lost(self):
        from test_output_profile import alt
        self.config['scanner']['output_profile'] = 'alt-pair-latin1'
        self.config['scan_send_enabled'] = True
        self.dashboard.begin_test()
        dashboard=self.dashboard
        stop=asyncio.Event()
        class Device:
            name='Simulated scanner'
            def grab(self): pass
            def close(self): pass
            async def async_read_loop(self):
                for code,value in alt(50189)+[(2,1),(2,0),(28,1)]:
                    yield SimpleNamespace(type=1,code=code,value=value)
                stop.set()
        evdev=SimpleNamespace(InputDevice=lambda path:Device(),ecodes=SimpleNamespace(EV_KEY=1))
        received=[]
        with patch.dict(sys.modules,evdev=evdev),patch('usb_scanner_mqtt.receiver.asyncio.sleep',new_callable=AsyncMock):
            asyncio.run(read_device(self.config,received.append,lambda value:None,stop,dashboard.observe))
        result=dashboard.snapshot()['test']
        self.assertEqual(result['layouts'],{layout:'Ä' for layout in ('us','de','gb','fr','es')})
        self.assertEqual(result['terminator'],'packed-13')
        self.assertFalse(dashboard.snapshot()['test_active'])
        self.assertTrue(dashboard.snapshot()['sending'])
        self.assertEqual(received,['1'])

    def test_calibration_detects_packed_profile_without_enabling_it(self):
        from test_output_profile import alt
        self.config['scanner']['output_profile']='standard'
        self.dashboard.begin_test()
        events=[(42,1),(21,1),(42,0),(21,0),(21,1),(21,0),(42,1),(44,1),(42,0),(44,0),(44,1),(44,0)] + alt(50189)
        for code,value in events:self.dashboard.observe(code,value)
        result=self.dashboard.snapshot()['test']
        self.assertFalse(self.dashboard.snapshot()['test_active'])
        self.assertEqual(self.config['scanner']['output_profile'],'standard')
        self.assertIsNone(result['layouts']['us'])
        self.assertEqual([candidate for candidate in result['candidates'] if candidate['text']=='YyZzÄ'],
                         [{'layout':layout,'output_profile':'alt-pair-latin1','text':'YyZzÄ'} for layout in ('us','gb','es')])
        self.assertTrue(result['terminator'].startswith('packed-'))

    def test_calibration_keeps_all_candidates_for_ambiguous_digits(self):
        self.dashboard.begin_test()
        for code,value in [(2,1),(2,0),(28,1)]:self.dashboard.observe(code,value)
        candidates=self.dashboard.snapshot()['test']['candidates']
        self.assertEqual(len(candidates),10)
        self.assertTrue(all(candidate['text']==('&' if candidate['layout']=='fr' else '1') for candidate in candidates))

    def test_language_catalog_exact_result_and_guarded_apply_api(self):
        from usb_scanner_mqtt.calibration import LANGUAGES
        from test_calibration import packed_input
        self.server()
        headers={'X-CSRF-Token':self.dashboard.token}
        status,body=self.request('GET','/api/calibration')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),LANGUAGES)
        self.assertEqual(self.request('POST','/api/test/start',{'language':'unknown'},headers)[0],400)
        self.assertEqual(self.request('POST','/api/calibration/apply',{},headers)[0],409)
        self.assertEqual(self.request('POST','/api/test/start',{'language':'de','expected':'wrong'},headers)[0],200)
        for code,value in packed_input(LANGUAGES['de']['text']):self.dashboard.observe(code,value)
        result=self.dashboard.snapshot()['test']
        self.assertEqual(result['expected'],LANGUAGES['de']['text'])
        self.assertEqual(result['comparison']['unique']['output_profile'],'alt-pair-latin1')
        saved=config.load(self.path)
        self.assertEqual(saved['scanner']['output_profile'],'standard')
        request={'test_id':result['test_id'],'language':'es'}
        self.assertEqual(self.request('POST','/api/calibration/apply',request,headers)[0],409)
        request['language']='de'
        self.assertEqual(self.request('POST','/api/calibration/apply',request,headers)[0],200)
        saved=config.load(self.path)
        self.assertEqual(saved['scanner']['layout'],'us')
        self.assertEqual(saved['scanner']['output_profile'],'alt-pair-latin1')
        self.assertEqual(saved['mqtt']['password'],'SECRET')
        self.reload.assert_called_once()
        self.dashboard.result_until=time.monotonic()-1
        self.assertEqual(self.request('POST','/api/calibration/apply',request,headers)[0],409)

    def test_manual_expected_text_is_frozen_and_ambiguous_result_cannot_apply(self):
        self.dashboard.begin_test(expected='1')
        for code,value in [(2,1),(2,0),(28,1)]:self.dashboard.observe(code,value)
        result=self.dashboard.snapshot()['test']
        self.assertEqual(result['expected'],'1')
        self.assertIsNone(result['comparison']['unique'])
        self.assertFalse(self.dashboard.apply_calibration(result['test_id']))
        self.assertEqual(config.load(self.path)['scanner']['output_profile'],'standard')

    def test_monitor_repeated_scans_extend_inactivity_and_restore_prior_sending(self):
        for enabled in (True,False):
            self.dashboard.clear_scans()
            self.config['scan_send_enabled']=enabled
            with patch('usb_scanner_mqtt.web.time.monotonic',return_value=10) as clock:
                self.dashboard.begin_scanning()
                self.assertEqual(self.dashboard.until,130)
                for now in (40,100):
                    clock.return_value=now
                    for code,value in [(11,1),(11,0),(2,1),(2,0),(28,1),(28,0)]:
                        self.assertTrue(self.dashboard.observe(code,value))
                    self.assertEqual(self.dashboard.until,now+120)
                state=self.dashboard.snapshot()
                self.assertTrue(state['scan_active'])
                self.assertFalse(state['test_active'])
                self.assertFalse(state['sending'])
                self.assertEqual([item['text'] for item in state['scan_items']],['01','01'])
                self.assertNotEqual(state['scan_items'][0]['id'],state['scan_items'][1]['id'])
                self.assertEqual(self.outbox.count(),0)
                clock.return_value=150
                self.dashboard.expire()  # The initial/previous deadline cannot end the renewed session.
                self.assertTrue(self.dashboard.snapshot()['scan_active'])
                clock.return_value=220
                self.dashboard.expire()
                state=self.dashboard.snapshot()
                self.assertFalse(state['scan_active'])
                self.assertFalse(self.publisher.test_paused.is_set())
                self.assertEqual(state['sending'],enabled)
                self.assertEqual([item['text'] for item in state['scan_items']],['01','01'])

    def test_monitor_uses_saved_profile_bounds_history_and_retains_on_stop(self):
        from test_output_profile import alt
        self.dashboard.begin_scanning()
        for code,value in alt(50189)+[(28,1)]:self.dashboard.observe(code,value)
        self.assertIsNone(self.dashboard.snapshot()['scan_items'][0]['text'])
        self.dashboard.stop_scanning()
        self.config['scanner']['output_profile']='alt-pair-latin1'
        self.dashboard.begin_scanning()
        for _ in range(23):
            for code,value in alt(50189)+[(28,1)]:self.dashboard.observe(code,value)
        state=self.dashboard.snapshot()
        self.assertEqual(len(state['scan_items']),20)
        self.assertTrue(all(item['text']=='Ä' for item in state['scan_items']))
        self.assertEqual(len({item['id'] for item in state['scan_items']}),20)
        self.assertIsNone(state['test'])
        self.dashboard.stop_scanning()
        self.assertFalse(self.publisher.test_paused.is_set())
        self.assertEqual(len(self.dashboard.snapshot()['scan_items']),20)
        self.dashboard.clear_scans()
        self.assertEqual(self.dashboard.snapshot()['scan_items'],[])

    def test_monitor_history_survives_restart_of_capture_calibration_and_expiry(self):
        with patch('usb_scanner_mqtt.web.time.monotonic',return_value=10) as clock:
            self.dashboard.begin_scanning()
            for code,value in [(2,1),(2,0),(28,1)]:self.dashboard.observe(code,value)
            original=self.dashboard.snapshot()['scan_items']
            self.dashboard.stop_scanning()
            self.dashboard.begin_scanning()
            self.assertEqual(self.dashboard.snapshot()['scan_items'],original)
            clock.return_value=200
            self.dashboard.expire()
            self.assertFalse(self.publisher.test_paused.is_set())
            self.assertEqual(self.dashboard.snapshot()['scan_items'],original)
            self.dashboard.begin_test(language='de')
            self.assertEqual(self.dashboard.snapshot()['scan_items'],original)
            self.dashboard.end_test()
            self.assertEqual(self.dashboard.snapshot()['scan_items'],original)
            self.dashboard.clear_scans()
            self.assertEqual(self.dashboard.snapshot()['scan_items'],[])

    def test_monitor_http_conflict_clear_and_stop(self):
        self.server()
        headers={'X-CSRF-Token':self.dashboard.token}
        self.assertEqual(self.request('POST','/api/scan/start',{},headers)[0],200)
        for code,value in [(2,1),(2,0),(28,1)]:self.dashboard.observe(code,value)
        deadline=self.dashboard.until
        self.assertEqual(self.request('POST','/api/test/start',{'language':'de'},headers)[0],409)
        self.assertEqual(self.request('POST','/api/scan/clear',{},headers)[0],200)
        self.assertEqual(self.dashboard.until,deadline)
        self.assertTrue(self.dashboard.snapshot()['scan_active'])
        self.assertEqual(self.dashboard.snapshot()['scan_items'],[])
        self.assertEqual(self.request('POST','/api/scan/stop',{},headers)[0],200)
        self.assertFalse(self.dashboard.snapshot()['scan_active'])
        self.assertEqual(self.request('POST','/api/test/start',{'language':'de'},headers)[0],200)
        self.assertEqual(self.request('POST','/api/scan/start',{},headers)[0],409)

    def test_monitor_does_not_forward_multiple_scans_and_resumes_next_real_scan(self):
        self.config['scan_send_enabled']=True
        self.dashboard.begin_scanning()
        dashboard=self.dashboard
        stop=asyncio.Event()
        class Device:
            name='Simulated scanner'
            def grab(self):pass
            def close(self):pass
            async def async_read_loop(self):
                for code,value in [(2,1),(2,0),(28,1),(28,0)]*2 + [(69,1),(69,0)]:
                    yield SimpleNamespace(type=1,code=code,value=value)
                dashboard.stop_scanning()
                for code,value in [(3,1),(3,0),(28,1)]:
                    yield SimpleNamespace(type=1,code=code,value=value)
                stop.set()
        evdev=SimpleNamespace(InputDevice=lambda path:Device(),ecodes=SimpleNamespace(EV_KEY=1))
        received=[]
        with patch.dict(sys.modules,evdev=evdev),patch('usb_scanner_mqtt.receiver.asyncio.sleep',new_callable=AsyncMock):
            asyncio.run(read_device(self.config,received.append,lambda value:None,stop,dashboard.observe))
        self.assertEqual(received,['2'])
        self.assertEqual([item['text'] for item in dashboard.snapshot()['scan_items']],['1','1'])

    def test_old_config_and_cli_options(self):
        old = copy.deepcopy(self.config)
        del old['web'], old['scan_send_enabled']
        config.validate(old)
        self.assertFalse(old['web']['enabled'])
        self.assertTrue(old['scan_send_enabled'])
        with patch('usb_scanner_mqtt.cli.root_required'), patch('usb_scanner_mqtt.cli.restart_if_running'):
            for key, value in (('gui', 'true'), ('web-port', '8766'), ('send', 'false'), ('output-profile', 'alt-pair-latin1')):
                self.assertEqual(main(['--config', str(self.path), 'set', key, value]), 0)
        saved = config.load(self.path)
        self.assertTrue(saved['web']['enabled'])
        self.assertEqual(saved['web']['port'], 8766)
        self.assertFalse(saved['scan_send_enabled'])
        self.assertEqual(saved['scanner']['output_profile'], 'alt-pair-latin1')

    def test_shell_setup_keeps_existing_values_and_asks_web_and_send(self):
        from usb_scanner_mqtt.cli import setup
        labels = []
        def ask(label, default=''):
            labels.append(label)
            if label.startswith('Enable internal'):
                return 'yes'
            if label.startswith('Send scans'):
                return 'no'
            return default
        with patch('usb_scanner_mqtt.cli.root_required'), patch('usb_scanner_mqtt.cli.restart_if_running'), patch('usb_scanner_mqtt.cli.available_devices', return_value=[]), patch('usb_scanner_mqtt.cli.ask', side_effect=ask):
            setup(self.path, mode='shell')
        saved = config.load(self.path)
        self.assertTrue(saved['web']['enabled'])
        self.assertFalse(saved['scan_send_enabled'])
        self.assertEqual(saved['mqtt']['password'], 'SECRET')
        self.assertTrue(any(label.startswith('Enable internal') for label in labels))
        self.assertTrue(any(label.startswith('Send scans') for label in labels))

    def test_paused_publisher_keeps_queue_and_resumes(self):
        self.outbox.put('scan', scan_payload('001', 'scanner'))
        publisher = Publisher.__new__(Publisher)
        publisher.control_lock = threading.Lock(); publisher.pending_controls = {}
        publisher.config = self.config
        publisher.outbox = self.outbox
        publisher.stop = threading.Event()
        publisher.connected = threading.Event()
        publisher.connected.set()
        publisher.scan_gate = threading.RLock()
        publisher.test_paused = threading.Event()
        publisher.publish_lock = threading.Lock()
        publisher.pending_mid = None
        publisher.registering_publish = False
        publisher.early_acks = {}
        publisher.pending_ack = threading.Event()
        publisher.client = Mock()
        publisher.client.publish.return_value = Mock(mid=1, rc=0)
        thread = threading.Thread(target=publisher.send_loop)
        thread.start()
        try:
            time.sleep(.2)
            publisher.client.publish.assert_not_called()
            self.assertEqual(self.outbox.count(), 1)
            publisher.test_paused.set()
            self.config['scan_send_enabled'] = True
            time.sleep(.2)
            publisher.client.publish.assert_not_called()
            self.assertEqual(self.outbox.count(), 1)
            publisher.test_paused.clear()
            deadline = time.monotonic() + 3
            while not publisher.client.publish.called and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(publisher.client.publish.called)
            publisher.on_publish(None, None, 1)
            deadline = time.monotonic() + 3
            while self.outbox.count() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(self.outbox.count(), 0)
        finally:
            publisher.stop.set()
            thread.join(3)


class ReceiverWebTests(unittest.TestCase):
    def test_new_scans_discarded_while_paused_and_queued_when_enabled(self):
        async def fake_read(config, consume, set_device, stop, observe=None):
            consume('00123')
            stop.set()
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                conf = config.defaults()
                conf['scan_send_enabled'] = enabled
                with patch('usb_scanner_mqtt.receiver.Publisher'), patch('usb_scanner_mqtt.receiver.read_device', fake_read):
                    self.assertFalse(asyncio.run(run_once(conf, directory, None)))
                outbox = Outbox(Path(directory) / 'outbox.sqlite3')
                try:
                    self.assertEqual(outbox.count(), int(enabled))
                    if enabled:
                        self.assertEqual(json.loads(outbox.first()[2])['ean'], '00123')
                finally:
                    outbox.close()
