"""Optional LAN dashboard with durable history and temporary calibration capture."""
import copy
import json
import secrets
import socket
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlsplit, parse_qs

from .auth import Auth, COOKIE, password_hash
from . import __version__, config as settings
from .keyboard import Decoder, LAYOUTS, LETTERS
from .diagnostics import diagnose_scan
from .calibration import LANGUAGES, compare_candidates


def keyboard_labels():
    labels = {}
    for layout, keys in LAYOUTS.items():
        labels[layout] = {code: char.upper() for code, char in LETTERS.items()}
        labels[layout].update({code: pair[0].upper() for code, pair in keys.items() if code != 57})
    labels['de'].update({21: 'Z', 44: 'Y'})
    labels['fr'].update({16: 'A', 30: 'Q', 17: 'Z', 44: 'W'})
    return labels


class AuthDenied(ValueError):
    pass


class CaptureBusy(ValueError):
    pass


class Dashboard:
    def __init__(self, config, path, publisher, outbox, reload, auth=None, history=None, control_changed=None):
        self.config, self.path = config, path
        self.publisher, self.outbox, self.reload = publisher, outbox, reload
        self.auth = auth if auth is not None else Auth(config['web'].get('auto_logout', False))
        self.auth.bind(config['web'])
        self.control_changed = control_changed
        self.history = history
        self.settings_lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.until = 0
        self.result_until = 0
        self.events = []
        self.result = None
        self.last_scan = None
        self.receive_error = None
        self.candidate_decoders = {}
        self.test_id = None
        self.test_expected = None
        self.test_language = None
        self.capture_mode = None
        self.scan_items = []
        self.scan_decoder = None
        self.timer = None
        self.last_event = 0

    def begin_test(self, language=None, expected=None, mode="calibration"):
        if self.config.get("setup_pending", False):
            raise ValueError("Complete setup first.")
        if language is not None:
            if language not in LANGUAGES:
                raise ValueError('Unsupported test language.')
            expected = LANGUAGES[language]['text']
        if expected is not None and (not isinstance(expected, str) or len(expected) > 4096):
            raise ValueError('Invalid expected test text.')
        with self.publisher.scan_gate, self.lock:
            if time.monotonic() < self.until and self.capture_mode != mode:
                raise CaptureBusy('Another capture mode is active.')
            self.capture_mode = mode
            self.scan_decoder = Decoder(self.config['scanner']['layout'], output_profile=self.config['scanner'].get('output_profile', 'standard'))
            self.publisher.test_paused.set()
            self.until = time.monotonic() + 120
            self.result_until = self.until
            self.events, self.result = [], None
            self.test_id = secrets.token_hex(16)
            self.test_expected, self.test_language = expected, language
            self.last_event = 0
            self.candidate_decoders = {(layout, profile): Decoder(layout, output_profile=profile) for layout in LAYOUTS for profile in ('standard', 'alt-pair-latin1')}
            self.arm_timer()

    def arm_timer(self):
        """Called with the state lock; one timer per capture, renewed on a scan."""
        if self.timer is not None:
            self.timer.cancel()
        self.timer = threading.Timer(120, self.expire)
        self.timer.daemon = True
        self.timer.start()

    def begin_scanning(self):
        self.begin_test(mode='scan')

    def stop_scanning(self):
        with self.lock:
            if self.capture_mode == 'scan':
                self.until = 0
                self.events = []
                self.scan_decoder = None
                self.publisher.test_paused.clear()
                # Stopping changes transmission only; entries remain until explicitly cleared.

    def clear_scans(self, scan_id=None):
        if scan_id is not None and (not isinstance(scan_id, str) or len(scan_id) > 64):
            raise ValueError('Invalid scan ID.')
        with self.lock:
            if self.history is not None:
                self.history.clear_history(scan_id)
            self.scan_items = [item for item in self.scan_items if item['id'] != scan_id] if scan_id else []

    def end_test(self):
        with self.lock:
            self.until = 0
            self.capture_mode = None
            self.scan_decoder = None
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            self.events, self.result, self.candidate_decoders = [], None, {}
            self.test_expected = self.test_language = None
            self.publisher.test_paused.clear()

    def expire(self):
        with self.lock:
            if time.monotonic() >= self.until:
                self.until = 0
                self.publisher.test_paused.clear()
            if time.monotonic() >= self.result_until:
                self.events, self.result, self.candidate_decoders = [], None, {}
                self.test_expected = self.test_language = None
                self.scan_decoder = None
                self.capture_mode = None

    def observe(self, code, value):
        with self.lock:
            now = time.monotonic()
            if now >= self.until:
                self.publisher.test_paused.clear()
                return False
            if now - self.last_event > 2:
                self.events = []
                if self.capture_mode == 'calibration':
                    self.candidate_decoders = {(layout, profile): Decoder(layout, output_profile=profile) for layout in LAYOUTS for profile in ('standard', 'alt-pair-latin1')}
            self.last_event = now
            self.events.append([code, value])
            if len(self.events) > 20000:
                self.until = 0
                self.events, self.result = [], None
                self.publisher.test_paused.clear()
                return True
            if self.capture_mode == 'scan':
                text = self.scan_decoder.feed(code, value, now)
                if self.scan_decoder.completed:
                    # Use only the saved decoder: monitoring must mirror normal reception.
                    # A trailing Enter after an embedded terminator is not another scan.
                    meaningful = any(value == 1 and code not in (28, 96, 15, 69)
                                     for code, value in self.events)
                    if meaningful:
                        self.last_scan = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        if self.history is not None:
                            from .receiver import scan_payload
                            payload = scan_payload(text, self.config['scanner']['id'])
                            self.history.record(payload, 'local', self.config.get('open_facts') if text is not None else None)
                        else:
                            self.scan_items.append({'id': secrets.token_hex(12), 'text': text,
                                                    'timestamp': self.last_scan,
                                                    'length': len(text) if text is not None else 0})
                            self.scan_items = self.scan_items[-20:]
                        self.until = now + 120
                        self.result_until = self.until
                        self.arm_timer()
                    self.events = []
                    return 'complete'
                return True
            candidate_results = {key: decoder.feed(code, value, now) for key, decoder in self.candidate_decoders.items()}
            profile = self.config['scanner'].get('output_profile', 'standard')
            decoded = {layout: candidate_results[(layout, profile)] for layout in LAYOUTS}
            completed = any(decoder.completed for decoder in self.candidate_decoders.values())
            if completed:
                self.result = {'text': decoded[self.config['scanner']['layout']],
                               'layouts': decoded, 'terminator': next(decoder.terminator for decoder in self.candidate_decoders.values() if decoder.completed),
                               'output_profile': self.config['scanner'].get('output_profile', 'standard'), 'events': self.events[:],
                               'candidates': [{'layout': layout, 'output_profile': profile, 'text': text}
                                              for (layout, profile), text in candidate_results.items() if text is not None],
                               'diagnostics': diagnose_scan(self.events, self.config['scanner'].get('output_profile', 'standard'))}
                self.result['test_id'] = self.test_id
                self.result['expected'] = self.test_expected
                self.result['language'] = self.test_language
                self.result['comparison'] = compare_candidates(self.result['candidates'], self.test_expected, self.events)
                self.last_scan = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                self.events = []
                self.until = 0
                self.publisher.test_paused.clear()
            # Captured events must never reach the normal receiver/outbox, including
            # the terminator that ends the temporary transmission pause.
            return 'complete' if completed else True

    def scan(self, text):
        with self.lock:
            self.last_scan = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    def snapshot(self):
        self.expire()
        with self.lock:
            active = time.monotonic() < self.until
            return {'setup_pending': self.config.get('setup_pending', False), 'auth_enabled': self.config['web'].get('auth_enabled', False), 'keyboard_labels': keyboard_labels(), 'version': __version__, 'scanner_connected': self.publisher.device_connected.is_set(),
                    'mqtt_connected': self.publisher.connected.is_set(), 'queued': self.outbox.count(),
                    'sending': self.config['scan_send_enabled'] and not active,
                    'send_enabled': self.config['scan_send_enabled'], 'receive_error': self.receive_error, 'last_scan': self.last_scan,
                    'open_facts_enabled': self.config.get('open_facts', {}).get('enabled', False),
                    'product_data_enabled': self.config.get('open_facts', {}).get('include_mqtt', True),
                    'test_remaining': max(0, int(self.until - time.monotonic()) + 1) if active else 0,
                    'capture_active': active, 'capture_mode': self.capture_mode,
                    'scan_active': active and self.capture_mode == 'scan',
                    'scan_remaining': max(0, int(self.until - time.monotonic()) + 1) if active and self.capture_mode == 'scan' else 0,
                    'scan_items': self.history.history() if self.history is not None else copy.deepcopy(self.scan_items),
                    'history_total': self.history.history_count() if self.history is not None else len(self.scan_items),
                    'test_active': active and self.capture_mode == 'calibration', 'test': copy.deepcopy(self.result),
                    'test_events': self.events[-200:] if active and self.capture_mode == 'calibration' else []}

    def apply_calibration(self, test_id, language=None):
        self.expire()
        with self.lock:
            if (not self.result or self.result.get('test_id') != test_id
                    or self.result.get('language') != language):
                return False
            unique = self.result['comparison']['unique']
            if unique is None:
                return False
            self.save({'scanner': {'layout': unique['layout'], 'output_profile': unique['output_profile']}})
            return True

    def public_config(self):
        result = copy.deepcopy(self.config)
        result['mqtt']['password'] = ''
        result['web'].pop('password_hash', None)
        result.pop('installation_id', None)
        return result

    def save(self, patch):
        with self.settings_lock:
            if self.path is None:
                raise ValueError('Configuration path unavailable.')
            # Read current disk state to preserve secrets changed through the CLI.
            config = settings.load(self.path)
            allowed = {'scanner': {'id', 'name', 'device', 'layout', 'topic', 'output_profile'},
                       'mqtt': {'host', 'port', 'user', 'password', 'tls', 'ca_file', 'discovery_prefix'},
                       'web': {'enabled', 'host', 'port', 'public_url'},
                       'history': {'limit'}, 'open_facts': {'enabled', 'include_mqtt', 'language', 'timeout'}}
            if not isinstance(patch, dict):
                raise ValueError('Expected settings object.')
            for section, values in patch.items():
                if section == 'scan_send_enabled':
                    config[section] = values
                    continue
                if section not in allowed or not isinstance(values, dict) or set(values) - allowed[section]:
                    raise ValueError('Unknown setting.')
                for key, value in values.items():
                    if section == 'mqtt' and key == 'password' and value == '':
                        continue
                    config[section][key] = value
            config['setup_pending'] = False
            settings.save(config, self.path)

    def set_control(self, key, value):
        from .mqtt_controls import CONTROLS
        if key not in CONTROLS or type(value) is not bool or self.path is None:
            raise ValueError('Unsupported MQTT control.')
        _, section, field, _ = CONTROLS[key]
        with self.publisher.scan_gate, self.settings_lock:
            config = settings.load(self.path)
            current = config[section][field] if section else config[field]
            if current != value:
                if section:
                    config[section][field] = value
                else:
                    config[field] = value
                settings.save(config, self.path)
            if section:
                self.config[section][field] = value
            else:
                self.config[field] = value
            if self.control_changed is not None:
                self.control_changed()

    def configure_auth(self, body):
        with self.settings_lock:
            enabled = body.get('enabled')
            auto_logout = body.get('auto_logout', False)
            if type(enabled) is not bool or type(auto_logout) is not bool:
                raise ValueError('Invalid authentication setting.')
            config = settings.load(self.path)
            web = config['web']
            if web['auth_enabled']:
                _, status = self.auth.login(body.get('current_password'), web['password_hash'], issue_session=False)
                if status != 200:
                    raise AuthDenied('Aktuelles Passwort prüfen; nach einem Fehlversuch bitte kurz warten.')
            # Disabling removes the password; re-enabling always requires a fresh explicit choice.
            encoded = ''
            if enabled:
                new_password = body.get('new_password', '')
                encoded = web['password_hash'] if web['auth_enabled'] and new_password == '' else password_hash(new_password)
            web.update(auth_enabled=enabled, password_hash=encoded, auto_logout=auto_logout)
            settings.save(config, self.path)
            self.config['web'].update(auth_enabled=enabled, password_hash=encoded, auto_logout=auto_logout)
            self.auth.bind(web, revoke=True)

    def start(self):
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value, content_type='application/json; charset=utf-8', cookie=None):
                data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
                self.send_response(status)
                if cookie is not None:
                    self.send_header('Set-Cookie', cookie)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' https://images.openfoodfacts.org https://images.openbeautyfacts.org https://images.openpetfoodfacts.org https://images.openproductsfacts.org; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                self.end_headers()
                self.wfile.write(data)

            def valid_host(self):
                try:
                    parsed = urlsplit('http://' + self.headers.get('Host', ''))
                    host = parsed.hostname
                    port = parsed.port or 80
                    allowed = {self.connection.getsockname()[0], 'localhost', socket.gethostname(),
                               socket.getfqdn(), dashboard.config['web']['host']}
                    public = dashboard.config['web'].get('public_url', '')
                    return ((host in allowed and port == self.server.server_port)
                            or bool(public and self.headers.get('Host', '') == urlsplit(public).netloc))
                except ValueError:
                    return False

            def session(self):
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get('Cookie', ''))
                    return cookie[COOKIE].value if COOKIE in cookie else ''
                except CookieError:
                    return ''

            def authenticated(self):
                return not dashboard.config['web'].get('auth_enabled', False) or dashboard.auth.valid(self.session())

            def session_cookie(self, value, clear=False):
                # The built-in server is HTTP. Direct TLS termination may add Secure;
                # never trust arbitrary forwarded headers to determine security.
                public = dashboard.config['web'].get('public_url', '')
                secure = public.startswith('https://') and (self.headers.get('Origin') == public
                          or self.headers.get('Host') == urlsplit(public).netloc)
                return f'{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict' + ('; Secure' if secure else '') + ('; Max-Age=0' if clear else '')

            def do_GET(self):
                if not self.valid_host():
                    self.reply(403, {'error': 'Invalid Host'})
                    return
                if self.path == '/api/auth':
                    self.reply(200, {'enabled': dashboard.config['web'].get('auth_enabled', False),
                                     'authenticated': self.authenticated(), 'token': dashboard.token,
                                     'auto_logout': dashboard.config['web'].get('auto_logout', False),
                                     'version': __version__})
                    return
                if self.path.startswith('/api/') and not self.authenticated():
                    self.reply(401, {'error': 'Bitte anmelden.'})
                    return
                if self.path == '/api/state':
                    self.reply(200, dashboard.snapshot())
                elif urlsplit(self.path).path == '/api/history':
                    try:
                        offset = int(parse_qs(urlsplit(self.path).query).get('offset', ['0'])[0])
                        if not 0 <= offset <= 10000:
                            raise ValueError()
                        self.reply(200, {'items': dashboard.history.history(offset=offset) if dashboard.history is not None else [],
                                         'total': dashboard.history.history_count() if dashboard.history is not None else 0})
                    except ValueError:
                        self.reply(400, {'error': 'Invalid history offset'})
                elif self.path == '/api/calibration':
                    self.reply(200, LANGUAGES)
                elif self.path == '/api/config':
                    self.reply(200, {'config': dashboard.public_config(), 'token': dashboard.token})
                elif self.path == '/api/devices':
                    from .cli import available_devices
                    self.reply(200, available_devices())
                elif self.path in ('/', '/app.js', '/i18n.js', '/style.css', '/qrcodegen.js'):
                    name, mime = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                                  '/i18n.js': ('i18n.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/qrcodegen.js': ('qrcodegen.js', 'text/javascript')}[self.path]
                    self.reply(200, files('usb_scanner_mqtt').joinpath('static', name).read_text(), mime + '; charset=utf-8')
                else:
                    self.reply(404, {'error': 'Not found'})

            def do_POST(self):
                origin = self.headers.get('Origin')
                if (not self.valid_host() or self.headers.get('X-CSRF-Token') != dashboard.token
                        or (origin and origin not in ('http://' + self.headers.get('Host', ''),
                                                     dashboard.config['web'].get('public_url', '')))):
                    self.reply(403, {'error': 'Invalid request origin or token'})
                    return
                if self.path != '/api/auth/login' and not self.authenticated():
                    self.reply(401, {'error': 'Bitte anmelden.'})
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 65536:
                        raise ValueError('Invalid request size.')
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise ValueError("Expected object.")
                    if self.path == '/api/auth/login':
                        if not dashboard.config['web'].get('auth_enabled', False):
                            self.reply(200, {'ok': True})
                            return
                        session, status = dashboard.auth.login(body.get('password'), dashboard.config['web']['password_hash'])
                        self.reply(status, {'ok': True} if session else {'error': 'Bitte kurz warten und das Passwort erneut prüfen.'},
                                   cookie=self.session_cookie(session) if session else None)
                    elif self.path == '/api/auth/logout':
                        dashboard.auth.logout(self.session())
                        self.reply(200, {'ok': True}, cookie=self.session_cookie('', clear=True))
                    elif self.path == '/api/auth/activity':
                        dashboard.auth.valid(self.session(), touch=True)
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/auth/settings':
                        dashboard.configure_auth(body)
                        self.reply(200, {'ok': True}, cookie=self.session_cookie('', clear=True))
                    elif self.path == '/api/config':
                        dashboard.save(body)
                        self.reply(200, {'ok': True, 'reloading': True})
                        dashboard.reload()
                    elif self.path == '/api/calibration/apply':
                        if dashboard.apply_calibration(body.get('test_id'), body.get('language')):
                            self.reply(200, {'ok': True, 'reloading': True})
                            dashboard.reload()
                        else:
                            self.reply(409, {'error': 'Kein eindeutiges aktuelles Testergebnis. Bitte neu kalibrieren.'})
                    elif self.path == '/api/scan/start':
                        dashboard.begin_scanning()
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/scan/stop':
                        dashboard.stop_scanning()
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/scan/clear':
                        dashboard.clear_scans(body.get('id'))
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/off/cache/clear':
                        if dashboard.history is not None:
                            dashboard.history.clear_cache()
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/test/start':
                        dashboard.begin_test(body.get('language'), body.get('expected'))
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/test/stop':
                        dashboard.end_test()
                        self.reply(200, {'ok': True})
                    else:
                        self.reply(404, {'error': 'Not found'})
                except AuthDenied as error:
                    self.reply(403, {'error': str(error)})
                except CaptureBusy:
                    self.reply(409, {'error': 'Bitte zuerst die laufende Aufnahme beenden.'})
                except (ValueError, KeyError, TypeError):
                    self.reply(400, {'error': 'Ungültige Eingabe. Bitte Werte prüfen.'})
                except OSError:
                    self.reply(500, {'error': 'Einstellungen konnten nicht gespeichert werden.'})

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(5)
                return connection, address

        server = Server((self.config['web']['host'], self.config['web']['port']), Handler)
        threading.Thread(target=server.serve_forever, name='scanner-web', daemon=True).start()
        return server
