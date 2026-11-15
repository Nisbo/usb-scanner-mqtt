"""Optional LAN dashboard. No scan contents are stored by the dashboard."""
import copy
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlsplit

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


class CaptureBusy(ValueError):
    pass


class Dashboard:
    def __init__(self, config, path, publisher, outbox, reload):
        self.config, self.path = config, path
        self.publisher, self.outbox, self.reload = publisher, outbox, reload
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.until = 0
        self.result_until = 0
        self.events = []
        self.result = None
        self.last_scan = None
        self.decoders = {}
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
            self.decoders = {layout: self.candidate_decoders[(layout, self.config['scanner'].get('output_profile', 'standard'))] for layout in LAYOUTS}
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

    def clear_scans(self):
        with self.lock:
            self.scan_items = []

    def end_test(self):
        with self.lock:
            self.until = 0
            self.capture_mode = None
            self.scan_decoder = None
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            self.events, self.result, self.decoders, self.candidate_decoders = [], None, {}, {}
            self.test_expected = self.test_language = None
            self.publisher.test_paused.clear()

    def expire(self):
        with self.lock:
            if time.monotonic() >= self.until:
                self.until = 0
                self.publisher.test_paused.clear()
            if time.monotonic() >= self.result_until:
                self.events, self.result, self.decoders, self.candidate_decoders = [], None, {}, {}
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
                    self.decoders = {layout: self.candidate_decoders[(layout, self.config['scanner'].get('output_profile', 'standard'))] for layout in LAYOUTS}
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
            return {'keyboard_labels': keyboard_labels(), 'version': __version__, 'scanner_connected': self.publisher.device_connected.is_set(),
                    'mqtt_connected': self.publisher.connected.is_set(), 'queued': self.outbox.count(),
                    'sending': self.config['scan_send_enabled'] and not active,
                    'send_enabled': self.config['scan_send_enabled'], 'last_scan': self.last_scan,
                    'test_remaining': max(0, int(self.until - time.monotonic()) + 1) if active else 0,
                    'capture_active': active, 'capture_mode': self.capture_mode,
                    'scan_active': active and self.capture_mode == 'scan',
                    'scan_remaining': max(0, int(self.until - time.monotonic()) + 1) if active and self.capture_mode == 'scan' else 0,
                    'scan_items': copy.deepcopy(self.scan_items),
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
        result.pop('installation_id', None)
        return result

    def save(self, patch):
        if self.path is None:
            raise ValueError('Configuration path unavailable.')
        # Read current disk state to preserve secrets changed through the CLI.
        config = settings.load(self.path)
        allowed = {'scanner': {'id', 'name', 'device', 'layout', 'topic', 'output_profile'},
                   'mqtt': {'host', 'port', 'user', 'password', 'tls', 'ca_file', 'discovery_prefix'},
                   'web': {'enabled', 'host', 'port'}}
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
        settings.save(config, self.path)

    def start(self):
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value, content_type='application/json; charset=utf-8'):
                data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                self.end_headers()
                self.wfile.write(data)

            def valid_host(self):
                try:
                    parsed = urlsplit('http://' + self.headers.get('Host', ''))
                    host = parsed.hostname
                    port = parsed.port or 80
                    allowed = {self.connection.getsockname()[0], 'localhost', socket.gethostname(),
                               socket.getfqdn(), dashboard.config['web']['host']}
                    return host in allowed and port == self.server.server_port
                except ValueError:
                    return False

            def do_GET(self):
                if not self.valid_host():
                    self.reply(403, {'error': 'Invalid Host'})
                    return
                if self.path == '/api/state':
                    self.reply(200, dashboard.snapshot())
                elif self.path == '/api/calibration':
                    self.reply(200, LANGUAGES)
                elif self.path == '/api/config':
                    self.reply(200, {'config': dashboard.public_config(), 'token': dashboard.token})
                elif self.path == '/api/devices':
                    from .cli import available_devices
                    self.reply(200, available_devices())
                elif self.path in ('/', '/app.js', '/style.css', '/qrcodegen.js'):
                    name, mime = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                                  '/style.css': ('style.css', 'text/css'), '/qrcodegen.js': ('qrcodegen.js', 'text/javascript')}[self.path]
                    self.reply(200, files('usb_scanner_mqtt').joinpath('static', name).read_text(), mime + '; charset=utf-8')
                else:
                    self.reply(404, {'error': 'Not found'})

            def do_POST(self):
                origin = self.headers.get('Origin')
                if (not self.valid_host() or self.headers.get('X-CSRF-Token') != dashboard.token
                        or (origin and origin != 'http://' + self.headers.get('Host', ''))):
                    self.reply(403, {'error': 'Invalid request origin or token'})
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 65536:
                        raise ValueError('Invalid request size.')
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise ValueError("Expected object.")
                    if self.path == '/api/config':
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
                        dashboard.clear_scans()
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/test/start':
                        dashboard.begin_test(body.get('language'), body.get('expected'))
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/test/stop':
                        dashboard.end_test()
                        self.reply(200, {'ok': True})
                    else:
                        self.reply(404, {'error': 'Not found'})
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
