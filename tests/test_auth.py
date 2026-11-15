import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from usb_scanner_mqtt import auth, config
from usb_scanner_mqtt.cli import main
from usb_scanner_mqtt.web import Dashboard

PASSWORD = 'A long test password Ö!'


class AuthTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'config.json'
        self.conf = config.defaults()
        self.conf['mqtt']['host'] = 'broker.example'
        self.conf['scanner']['device'] = '/dev/input/test'
        config.save(self.conf, self.path)
        publisher = Mock()
        publisher.scan_gate = threading.RLock()
        publisher.test_paused = threading.Event()
        publisher.device_connected = threading.Event()
        publisher.connected = threading.Event()
        self.dashboard = Dashboard(self.conf, self.path, publisher, Mock(count=lambda: 0), Mock())
        self.addCleanup(self.dashboard.end_test)
        self.conf['web'].update(host='127.0.0.1', port=0)
        self.server = self.dashboard.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.headers = {'X-CSRF-Token': self.dashboard.token}

    def request(self, method, path, body=None, cookie=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        request_headers = {**self.headers, **(headers or {})}
        if cookie: request_headers['Cookie'] = cookie
        connection.request(method, path, json.dumps(body) if body is not None else None, request_headers)
        response = connection.getresponse()
        status, data, response_headers = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return status, json.loads(data), response_headers

    def enable(self):
        self.assertEqual(self.request('POST', '/api/auth/settings', {'enabled': True, 'new_password': PASSWORD})[0], 200)

    def login(self, password=PASSWORD):
        status, _, headers = self.request('POST', '/api/auth/login', {'password': password})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        return cookie.split(';')[0]

    def test_disabled_default_and_hash_redaction(self):
        self.assertFalse(config.load(self.path)['web']['auth_enabled'])
        self.assertEqual(config.load(self.path)['web']['password_hash'], '')
        self.assertEqual(self.request('GET', '/api/state')[0], 200)
        self.enable()
        saved = config.load(self.path)['web']['password_hash']
        self.assertTrue(auth.verify(PASSWORD, saved))
        self.assertNotIn(PASSWORD, self.path.read_text())
        cookie = self.login()
        status, body, _ = self.request('GET', '/api/config', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertNotIn('password_hash', body['config']['web'])
        self.assertNotIn(saved, json.dumps(body))
        self.assertEqual(self.request('POST', '/api/config', {'mqtt': {'port': 1884}}, cookie)[0], 200)
        self.assertEqual(config.load(self.path)['web']['password_hash'], saved)
        self.assertTrue(config.load(self.path)['web']['auth_enabled'])
        # Generic settings cannot bypass the authenticated password management path.
        self.assertEqual(self.request('POST', '/api/config', {'web': {'auth_enabled':False}}, cookie)[0],400)

    def test_every_private_route_requires_login_and_mutations_require_csrf(self):
        self.enable()
        for path in ('/api/state','/api/config','/api/devices','/api/calibration'):
            self.assertEqual(self.request('GET',path)[0],401,path)
        for path in ('/api/config','/api/scan/start','/api/scan/clear','/api/test/start',
                     '/api/calibration/apply','/api/auth/settings','/api/auth/activity','/api/auth/logout'):
            self.assertEqual(self.request('POST',path,{})[0],401,path)
        cookie=self.login()
        self.assertEqual(self.request('POST','/api/scan/start',{},cookie,{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('POST','/api/auth/settings',{},cookie,{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('GET','/api/config',cookie='scanner_session=forged')[0],401)
        self.assertEqual(self.request('GET','/api/auth')[1]['authenticated'],False)

    def test_change_disable_and_logout_revoke_sessions_and_preserve_settings(self):
        original=config.load(self.path)
        self.enable(); cookie=self.login(); other=self.login()
        self.assertEqual(self.request('POST','/api/auth/settings',{'enabled':False,'current_password':'wrong'},cookie)[0],403)
        self.assertTrue(config.load(self.path)['web']['auth_enabled'])
        self.dashboard.auth.blocked_until = 0  # Simulate waiting out the failed re-authentication backoff.
        updated='Another long password!'
        self.assertEqual(self.request('POST','/api/auth/settings',{'enabled':True,'current_password':PASSWORD,'new_password':updated},cookie)[0],200)
        for old in (cookie,other):self.assertEqual(self.request('GET','/api/config',cookie=old)[0],401)
        self.assertFalse(auth.verify(PASSWORD,config.load(self.path)['web']['password_hash']))
        cookie=self.login(updated)
        self.assertEqual(self.request('POST','/api/auth/logout',{},cookie)[0],200)
        self.assertEqual(self.request('GET','/api/config',cookie=cookie)[0],401)
        cookie=self.login(updated)
        self.assertEqual(self.request('POST','/api/auth/settings',{'enabled':False,'current_password':updated},cookie)[0],200)
        saved=config.load(self.path)
        self.assertEqual(saved,original)
        self.assertEqual(self.request('GET','/api/state')[0],200)
        self.assertEqual(self.dashboard.auth.sessions,{})

    def test_shell_reset_keeps_mqtt_and_scanner_and_requires_root(self):
        original=config.load(self.path); self.enable()
        with patch('usb_scanner_mqtt.cli.root_required',side_effect=ValueError('root required')):
            self.assertEqual(main(['--config',str(self.path),'reset-login']),1)
        self.assertTrue(config.load(self.path)['web']['auth_enabled'])
        with patch('usb_scanner_mqtt.cli.root_required'),patch('usb_scanner_mqtt.cli.restart_if_running') as restart:
            self.assertEqual(main(['--config',str(self.path),'reset-login']),0)
            restart.assert_called_once()
        self.assertEqual(config.load(self.path),original)

    def test_login_throttling_session_expiry_and_explicit_activity(self):
        self.enable()
        with patch('usb_scanner_mqtt.auth.time.monotonic',return_value=100) as clock:
            self.assertEqual(self.request('POST','/api/auth/login',{'password':'wrong'})[0],401)
            self.assertEqual(self.request('POST','/api/auth/login',{'password':PASSWORD})[0],429)
            clock.return_value=103
            cookie=self.login()
            clock.return_value=103+auth.IDLE_SECONDS-1
            self.assertEqual(self.request('GET','/api/config',cookie=cookie)[0],200)
            clock.return_value=103+auth.IDLE_SECONDS
            self.assertEqual(self.request('GET','/api/config',cookie=cookie)[0],401)
            cookie=self.login()
            clock.return_value+=auth.IDLE_SECONDS-1
            self.assertEqual(self.request('POST','/api/auth/activity',{},cookie)[0],200)
            clock.return_value+=2
            self.assertEqual(self.request('GET','/api/config',cookie=cookie)[0],200)
            clock.return_value+=auth.MAX_SECONDS
            self.assertEqual(self.request('GET','/api/config',cookie=cookie)[0],401)

    def test_auth_changes_preserve_local_scans_and_transmission_pause(self):
        self.dashboard.begin_scanning()
        for code, value in ((2,1), (2,0), (28,1)):
            self.dashboard.observe(code, value)
        items = copy.deepcopy(self.dashboard.scan_items)
        self.enable()
        self.assertEqual(self.dashboard.scan_items, items)
        self.assertTrue(self.dashboard.publisher.test_paused.is_set())
        self.assertTrue(self.dashboard.snapshot()['scan_active'])
        self.dashboard.stop_scanning()
        self.assertFalse(self.dashboard.publisher.test_paused.is_set())

    def test_invalid_password_and_config_rejected_without_modification(self):
        for password in ('short', 'x'*1025, None):
            self.assertEqual(self.request('POST','/api/auth/settings',{'enabled':True,'new_password':password})[0],400)
            self.assertFalse(config.load(self.path)['web']['auth_enabled'])
        for value in ('bogus', 'pbkdf2-sha256$999999999$00$00'):
            conf=config.load(self.path); conf['web'].update(auth_enabled=True,password_hash=value)
            with self.assertRaises(ValueError):config.validate(conf)
        first=auth.password_hash(PASSWORD); second=auth.password_hash(PASSWORD)
        self.assertNotEqual(first,second)
        self.assertFalse(auth.verify('wrong', first))
