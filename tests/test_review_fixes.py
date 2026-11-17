"""Regression coverage for the reviewed failure paths."""
import asyncio
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from usb_scanner_mqtt import config
from usb_scanner_mqtt.receiver import Publisher, SetupPublisher, run_once, scan_payload
from usb_scanner_mqtt.storage import Outbox


class ReviewFixTests(unittest.TestCase):
    def test_negative_broker_ack_retries_same_scan_and_then_drains(self):
        p = Publisher.__new__(Publisher)
        p.config = config.defaults()
        p.stop = threading.Event(); p.connected = threading.Event(); p.connected.set()
        p.test_paused = threading.Event(); p.scan_gate = threading.RLock()
        p.publish_lock = threading.Lock(); p.pending_ack = threading.Event()
        p.pending_mid = None; p.early_acks = {}; p.registering_publish = False
        p.process_controls = lambda: None
        p.outbox = Mock(); p.outbox.first.return_value = (1, 'original/topic', '{"scan_id":"same-id"}')
        p.outbox.remove.side_effect = lambda value: p.stop.set()
        p.client = Mock()
        attempts = []
        def publish(topic, payload, **kwargs):
            attempts.append((topic, payload, kwargs))
            p.on_publish(None, None, len(attempts), SimpleNamespace(is_failure=len(attempts) == 1))
            return SimpleNamespace(mid=len(attempts), rc=0)
        p.client.publish.side_effect = publish
        # Remove only the explicit retry delay, preserving actual ACK handling.
        original_wait = p.stop.wait
        p.stop.wait = lambda timeout=None: original_wait(0)
        p.send_loop()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], attempts[1])
        self.assertFalse(attempts[0][2]['retain'])
        p.outbox.remove.assert_called_once_with(1)

    def test_full_outbox_keeps_receiver_running_and_records_unsent_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            conf = config.defaults(); conf['mqtt']['host'] = 'broker'; conf['scanner']['device'] = '/dev/input/test'
            config.save(conf, path)
            store = Outbox(Path(directory)/'outbox.sqlite3')
            for i in range(1000): store.put('old/topic', scan_payload(str(i), 'scanner'))
            store.close()
            class FakePublisher(SetupPublisher):
                def __init__(self, *args): super().__init__()
                def start(self): pass
                def set_device(self, value): pass
            async def read(conf, consume, device, stop, observe):
                consume('00123')
                stop.set()
            with patch('usb_scanner_mqtt.receiver.Publisher', FakePublisher), patch('usb_scanner_mqtt.receiver.read_device', read), patch('usb_scanner_mqtt.open_facts.Enricher'):
                self.assertFalse(asyncio.run(run_once(conf, directory, path)))
            store = Outbox(Path(directory)/'outbox.sqlite3')
            try:
                self.assertEqual(store.count(), 1000)
                self.assertEqual(store.history()[0]['text'], '00123')
                self.assertEqual(store.history()[0]['status'], 'queue_full')
            finally: store.close()

    def test_devices_without_alias_are_not_hidden_by_other_keyboard(self):
        from usb_scanner_mqtt.cli import available_devices
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'by-id').mkdir()
            (root/'event0').touch(); (root/'event1').touch()
            (root/'by-id/keyboard-event-kbd').symlink_to(root/'event0')
            def paths(value):
                return root if value == '/dev/input' else root/'by-id' if value == '/dev/input/by-id' else root/'missing'
            with patch('usb_scanner_mqtt.cli.Path', side_effect=paths):
                found = available_devices()
            self.assertEqual(found, [str(root/'by-id/keyboard-event-kbd'), str(root/'event1')])

    def test_public_url_validation_rejects_credentials_paths_and_bad_ports(self):
        for url in ('https://user:pw@example.org', 'https://example.org/path', 'https://example.org/', 'https://example.org:0', 'https://example.org:99999', 'javascript:alert(1)'):
            conf = config.defaults(); conf['setup_pending'] = True; conf['web'].update(enabled=True, public_url=url)
            with self.subTest(url=url), self.assertRaises(ValueError): config.validate(conf)
