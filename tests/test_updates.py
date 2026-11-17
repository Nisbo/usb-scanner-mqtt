import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from usb_scanner_mqtt import config, updates, update_http
from usb_scanner_mqtt.cli import main

A, B = 'a' * 40, 'b' * 40


class UpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(update_http, 'CACHE_DIR', Path(directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def response(self, data):
        value = Mock()
        value.__enter__ = Mock(return_value=value)
        value.__exit__ = Mock(return_value=False)
        value.read.return_value = data
        return value

    def test_release_resolution_pins_version_and_commit(self):
        for channel in ('stable', 'prerelease', 'dev'):
            with self.subTest(channel=channel):
                release = {'tag_name': 'v0.13.0', 'prerelease': False}
                def github(path):
                    if path == '/releases/latest': return release
                    if path.startswith('/releases?'): return [release, {'tag_name': 'v0.14.0-rc.1', 'prerelease': True, 'draft': True}]
                    return {'sha': B}
                with patch.object(updates, 'github', side_effect=github) as calls, patch.object(updates.urllib.request, 'urlopen', return_value=self.response(b'__version__ = "0.13.0"\n')) as fetch:
                    result = updates.resolve(channel)
                self.assertEqual(result['revision'], B)
                self.assertIn('/' + B + '/', fetch.call_args.args[0])
                self.assertNotIn('main', str(calls.call_args_list))
                self.assertEqual(bool(result['release_url']), channel != 'dev')

    def test_prereleases_are_sorted_by_version_not_api_order(self):
        releases = [{'tag_name': 'v0.13.1-rc.2', 'prerelease': True}, {'tag_name': 'v0.13.0'}, {'tag_name': 'v0.13.1-rc.10', 'prerelease': True}, {'tag_name': '../bad'}]
        with patch.object(updates, 'github', side_effect=[releases, {'sha': B}]), patch.object(updates.urllib.request, 'urlopen', return_value=self.response(b'__version__ = "0.13.1-rc.10"\n')):
            self.assertEqual(updates.resolve('prerelease')['version'], '0.13.1-rc.10')

    def test_downgrades_and_divergent_commits_are_blocked(self):
        for version, status, expected in [('0.12.0', 'ahead', 'waiting'), ('0.13.0', 'behind', 'waiting'), ('0.13.0', 'diverged', 'waiting'), ('0.13.0', 'ahead', 'available'), ('0.14.0', 'ahead', 'available')]:
            with self.subTest(version=version, status=status), patch.object(updates, 'github', return_value={'status': status}):
                value = updates.assess({'version': version, 'revision': B, 'channel': 'dev'}, '0.13.0', A)
                self.assertEqual(value['status'], expected)
                if expected == 'available':
                    self.assertTrue(value['changes_url'].endswith('/compare/' + A + '...' + B))
        with patch.object(updates, 'github') as api:
            self.assertFalse(updates.assess({'version': '0.13.0', 'revision': A, 'channel': 'stable'}, '0.13.0', A)['available'])
            api.assert_not_called()
        self.assertGreater(updates.version_key('0.13.0'), updates.version_key('0.13.0-rc.10'))

    def test_unknown_installed_revision_is_conservative(self):
        self.assertFalse(updates.assess({'version': '0.13.0', 'revision': B, 'channel': 'dev'}, '0.13.0')['available'])
        self.assertTrue(updates.assess({'version': '0.14.0', 'revision': B, 'channel': 'stable'}, '0.13.0')['available'])

    def test_pinned_installer_and_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conf = config.defaults(); conf['setup_pending'] = True; conf['web']['enabled'] = True
            path = root / 'config.json'; config.save(conf, path)
            target = {'version': '0.14.0', 'revision': B, 'channel': 'stable', 'available': True}
            with patch.object(config, 'DEFAULT_CONFIG', path), patch.object(updates, 'STATE_DIR', root), patch.object(updates, 'write_status', side_effect=lambda value: (root / 'status').write_text(json.dumps(value))), patch.object(updates, 'check', return_value=target), patch.object(updates.urllib.request, 'urlopen', return_value=self.response(b'#!/bin/bash\nexit 0\n')) as fetch, patch.object(updates.subprocess, 'run') as run:
                updates.install(path, B, True)
                self.assertIn('/' + B + '/install.sh', fetch.call_args.args[0])
                self.assertIn('--revision=' + B, run.call_args.args[0])
                self.assertIn('--non-interactive', run.call_args.args[0])
                self.assertEqual(json.loads((root / 'status').read_text())['phase'], 'complete')
                with self.assertRaises(ValueError): updates.install(path, A)
                self.assertEqual(json.loads((root / 'status').read_text())['phase'], 'error')
                with patch.object(updates, 'check', side_effect=updates.UpdateError('GitHub request limit reached.', 'rate_limit', 2000)):
                    with self.assertRaises(updates.UpdateError): updates.install(path, B)
                failed = json.loads((root / 'status').read_text())
                self.assertEqual(failed['error_code'], 'rate_limit')
                self.assertEqual(failed['retry_at'], 2000)


    def test_shell_channel_preserves_settings_and_only_check_does_not_install(self):
        with tempfile.TemporaryDirectory() as directory:
            conf = config.defaults(); conf['setup_pending'] = True; conf['web']['enabled'] = True
            conf['mqtt']['password'] = 'test-secret'
            path = Path(directory) / 'config.json'; config.save(conf, path)
            with patch('usb_scanner_mqtt.cli.root_required'), patch('usb_scanner_mqtt.cli.restart_if_running'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--config', str(path), 'channel', 'dev']), 0)
            saved = config.load(path)
            self.assertEqual(saved['mqtt']['password'], 'test-secret')
            self.assertEqual(saved['update_channel'], 'dev')
            with patch.object(updates, 'check', return_value={'available': False, 'status': 'current', 'installed_version': '0.13.0', 'channel': 'dev', 'version': '0.13.0', 'revision': B, 'url': 'https://github.com/Nisbo/usb-scanner-mqtt/commits/dev/'}) as check, patch.object(updates, 'install') as install, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--config', str(path), 'update', '--check']), 0)
                check.assert_called_once_with('dev'); install.assert_not_called()

    def test_interrupted_update_status_and_old_config_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            updates.write_status({'phase': 'installing'}, root)
            with patch.object(updates.os, 'kill', side_effect=ProcessLookupError):
                self.assertEqual(updates.read_status(root)['phase'], 'error')
            (root/'update-status.json').write_text('[]')
            self.assertEqual(updates.read_status(root), {'phase': 'idle'})
        conf = config.defaults(); conf.pop('update_channel')
        conf['setup_pending'] = True; conf['web']['enabled'] = True
        self.assertEqual(config.validate(conf)['update_channel'], 'stable')
        conf['update_channel'] = 'unknown'
        with self.assertRaises(ValueError): config.validate(conf)

    def test_new_check_clears_previous_completion_but_not_running_update(self):
        from types import SimpleNamespace
        dashboard = SimpleNamespace(config={'update_channel': 'dev'})
        manager = updates.UpdateManager(dashboard)
        finished = threading.Event()
        with patch.object(updates, 'read_status', return_value={'phase': 'complete'}), patch.object(updates, 'write_status') as write, patch.object(updates, 'check', side_effect=lambda channel: finished.set() or {'available': False}):
            manager.start_check()
            self.assertTrue(finished.wait(2))
            write.assert_called_once_with({'phase': 'idle'})
        manager = updates.UpdateManager(dashboard)
        with patch.object(updates, 'read_status', return_value={'phase': 'installing'}), patch.object(updates, 'write_status') as write:
            with self.assertRaises(ValueError): manager.start_check()
            write.assert_not_called()

    def test_network_failure_has_no_secret_or_remote_body(self):
        with patch.object(updates.urllib.request, 'urlopen', side_effect=OSError('private response')):
            with self.assertRaisesRegex(ValueError, 'Update check failed') as error:
                updates.github('/releases/latest')
            self.assertNotIn('private response', str(error.exception))
