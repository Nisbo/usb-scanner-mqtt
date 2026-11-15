"""Manual HA product queries, deliberately isolated from scanner messages."""
import json
import logging
import re
import sqlite3
import threading

from . import mqtt_controls as controls

LOG = logging.getLogger(__name__)


def topic(config, suffix):
    return controls.base_topic(config) + '/lookup/' + suffix


def discovery(config):
    prefix = config['mqtt']['discovery_prefix'].rstrip('/')
    common = {'device': controls.device(config), 'qos': 1,
              'availability_topic': controls.base_topic(config) + '/status/availability',
              'payload_available': 'online', 'payload_not_available': 'offline'}
    entries = [
        ('text', 'lookup_ean', {'name': 'Product query: EAN', 'icon': 'mdi:barcode-scan',
             'command_topic': topic(config, 'ean/set'), 'state_topic': topic(config, 'ean/state'),
             'value_template': '{{ value_json.ean }}', 'mode': 'text', 'min': 0, 'max': 32, 'pattern': '^[0-9]{0,32}$', 'retain': False}),
        ('button', 'lookup_start', {'name': 'Product query: Start lookup', 'icon': 'mdi:magnify',
             'command_topic': topic(config, 'start'), 'payload_press': 'LOOKUP', 'retain': False}),
        ('sensor', 'lookup_result', {'name': 'Product query: Result', 'icon': 'mdi:package-variant',
             'state_topic': topic(config, 'result'), 'value_template': '{{ value_json.state }}',
             'json_attributes_topic': topic(config, 'result')}),
    ]
    return [(f'{prefix}/{kind}/{controls.identity(config)}/{key}/config',
             {**common, **payload, 'unique_id': controls.identity(config) + '_' + key,
              'default_entity_id': kind + '.' + controls.entity_slug(config) + '_' + key})
            for kind, key, payload in entries]


class ManualLookup:
    """Bounded callback staging; all SQLite access happens on the worker."""
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.lock = threading.Lock()
        self.public = self.snapshot()
        self.code = self.public[0]
        self.pending_input = None
        self.pending_start = None
        self.sent = None

    def snapshot(self):
        value = self.store.manual_snapshot()
        return value['ean'], json.dumps(value['result'], ensure_ascii=False)

    def accept(self, command_topic, payload):
        if command_topic == topic(self.config, 'ean/set'):
            if len(payload) > 32 or not re.fullmatch(b'[0-9]*', payload):
                return
            with self.lock:
                self.code = payload.decode('ascii')
                self.pending_input = self.code
        elif command_topic == topic(self.config, 'start') and payload == b'LOOKUP':
            with self.lock:
                self.pending_start = self.code  # Capture the EAN at button press.

    def process(self):
        with self.lock:
            code, start = self.pending_input, self.pending_start
            self.pending_input = self.pending_start = None
        try:
            if code is not None:
                self.store.manual_set_input(code)
            if start is not None:
                self.store.manual_start(start, self.config['open_facts'])
        except (OSError, sqlite3.Error, ValueError):
            LOG.warning('Manual product query could not be saved.')
            # Reconfirm the saved input; never leave an optimistic, unpersisted EAN.
            saved = self.store.manual_snapshot()['ean']
            with self.lock:
                if self.pending_input is None:
                    self.code = saved
        current = self.snapshot()
        with self.lock:
            self.public = current

    def publish(self, client, force=False):
        with self.lock:
            current = self.public
            if not force and current == self.sent:
                return
        # Publish only these dedicated topics, never the scanner topic.
        first = client.publish(topic(self.config, 'ean/state'), json.dumps({'ean': current[0]}), qos=1, retain=True)
        second = client.publish(topic(self.config, 'result'), current[1], qos=1, retain=True)
        if first.rc == 0 and second.rc == 0:
            with self.lock:
                self.sent = current
