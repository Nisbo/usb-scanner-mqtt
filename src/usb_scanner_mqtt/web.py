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
from .keyboard import Decoder


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
        self.last_event = 0

    def begin_test(self):
        with self.publisher.scan_gate, self.lock:
            self.publisher.test_paused.set()
            self.until = time.monotonic() + 120
            self.result_until = self.until
            self.events, self.result = [], None
            self.last_event = 0
            self.decoders = {layout: Decoder(layout) for layout in ('us', 'de')}
        timer = threading.Timer(120, self.expire)
        timer.daemon = True
        timer.start()

    def end_test(self):
        with self.lock:
            self.until = 0
            self.events, self.result, self.decoders = [], None, {}
            self.publisher.test_paused.clear()

    def expire(self):
        with self.lock:
            if time.monotonic() >= self.until:
                self.until = 0
                self.publisher.test_paused.clear()
            if time.monotonic() >= self.result_until:
                self.events, self.result, self.decoders = [], None, {}

    def observe(self, code, value):
        with self.lock:
            now = time.monotonic()
            if now >= self.until:
                self.publisher.test_paused.clear()
                return False
            if now - self.last_event > 2:
                self.events = []
                self.decoders = {layout: Decoder(layout) for layout in ('us', 'de')}
            self.last_event = now
            self.events.append([code, value])
            if len(self.events) > 20000:
                self.until = 0
                self.events, self.result = [], None
                self.publisher.test_paused.clear()
                return True
            decoded = {layout: decoder.feed(code, value, now) for layout, decoder in self.decoders.items()}
            if value == 1 and code in (28, 96, 15):
                self.result = {'text': decoded[self.config['scanner']['layout']],
                               'layouts': decoded, 'terminator': code, 'events': self.events[:]}
                self.last_scan = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                self.events = []
                self.until = 0
                self.publisher.test_paused.clear()
            # Captured events must never reach the normal receiver/outbox, including
            # the terminator that ends the temporary transmission pause.
            return True

    def scan(self, text):
        with self.lock:
            self.last_scan = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    def snapshot(self):
        self.expire()
        with self.lock:
            active = time.monotonic() < self.until
            return {'version': __version__, 'scanner_connected': self.publisher.device_connected.is_set(),
                    'mqtt_connected': self.publisher.connected.is_set(), 'queued': self.outbox.count(),
                    'sending': self.config['scan_send_enabled'] and not active,
                    'send_enabled': self.config['scan_send_enabled'], 'last_scan': self.last_scan,
                    'test_remaining': max(0, int(self.until - time.monotonic()) + 1) if active else 0,
                    'test_active': active, 'test': copy.deepcopy(self.result),
                    'test_events': self.events[-200:] if active else []}

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
        allowed = {'scanner': {'id', 'name', 'device', 'layout', 'topic'},
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
                    if self.path == '/api/config':
                        dashboard.save(body)
                        self.reply(200, {'ok': True, 'reloading': True})
                        dashboard.reload()
                    elif self.path == '/api/test/start':
                        dashboard.begin_test()
                        self.reply(200, {'ok': True})
                    elif self.path == '/api/test/stop':
                        dashboard.end_test()
                        self.reply(200, {'ok': True})
                    else:
                        self.reply(404, {'error': 'Not found'})
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
