"""Browser bootstrap, setup completion, IPv4 addresses and isolated uninstall tests."""
import asyncio
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from usb_scanner_mqtt import config
from usb_scanner_mqtt.cli import main, setup
from usb_scanner_mqtt.maintenance import ipv4_addresses, web_urls, remove_installation, uninstall
from usb_scanner_mqtt.receiver import SetupPublisher, run_once, Outbox
from usb_scanner_mqtt.web import Dashboard


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.path=self.root/'config.json'

    def browser_setup(self):
        with patch('usb_scanner_mqtt.cli.root_required'), patch('usb_scanner_mqtt.cli.restart_if_running'), \
             patch('usb_scanner_mqtt.cli.ask',return_value='1') as ask, \
             patch('usb_scanner_mqtt.maintenance.ipv4_addresses',return_value=['192.0.2.10','192.0.2.20']), \
             patch('sys.stdout',new_callable=io.StringIO) as output:
            setup(self.path)
            self.assertEqual(ask.call_count,1)  # No MQTT or scanner questions in browser mode.
            self.assertIn('http://192.0.2.10:8765',output.getvalue())
            self.assertIn('http://192.0.2.20:8765',output.getvalue())
        return config.load(self.path)

    def test_browser_default_needs_no_device_or_broker_and_first_save_is_strict(self):
        conf=self.browser_setup()
        self.assertTrue(conf['setup_pending']);self.assertTrue(conf['web']['enabled'])
        self.assertFalse(conf['web']['auth_enabled']);self.assertEqual(conf['web']['password_hash'],'')
        outbox=Outbox(self.root/'outbox.db');self.addCleanup(outbox.close)
        reload=Mock();dashboard=Dashboard(conf,self.path,SetupPublisher(),outbox,reload)
        self.addCleanup(dashboard.end_test)
        with self.assertRaises(ValueError):dashboard.save({'mqtt':{'host':'broker.example'}})
        self.assertTrue(config.load(self.path)['setup_pending'])
        with self.assertRaises(ValueError):dashboard.begin_scanning()
        dashboard.save({'mqtt':{'host':'broker.example'},'scanner':{'device':'/dev/input/test','name':'Küche'}})
        saved=config.load(self.path)
        self.assertFalse(saved['setup_pending']);self.assertEqual(saved['scanner']['name'],'Küche')
        self.assertNotIn('\\u00fc',self.path.read_text())

    def test_pending_receiver_does_not_start_mqtt_or_read_usb_and_can_reload(self):
        conf=self.browser_setup();server=Mock()
        def start(dashboard):
            dashboard.reload()
            return server
        with patch('usb_scanner_mqtt.receiver.Publisher') as mqtt, \
             patch('usb_scanner_mqtt.receiver.read_device',new_callable=AsyncMock) as usb, \
             patch('usb_scanner_mqtt.web.Dashboard.start',autospec=True,side_effect=start):
            self.assertTrue(asyncio.run(run_once(conf,self.root,self.path)))
        mqtt.assert_not_called();usb.assert_not_awaited();server.shutdown.assert_called_once()

    def test_browser_choice_preserves_existing_configuration_and_data(self):
        conf=config.defaults();conf['mqtt'].update(host='broker.example',password='private')
        conf['scanner']['device']='/dev/input/test';config.save(conf,self.path)
        with patch('usb_scanner_mqtt.cli.root_required'),patch('usb_scanner_mqtt.cli.restart_if_running'), \
             patch('usb_scanner_mqtt.maintenance.print_web_addresses'):
            setup(self.path,mode='browser')
        saved=config.load(self.path);conf['web']['enabled']=True
        self.assertEqual(saved,conf);self.assertFalse(saved['setup_pending'])

    def test_shell_choice_device_number_defaults_and_unicode_name(self):
        def answer(label,default=''):
            if label=='Choice / Auswahl':return '2'
            if label.startswith('Scanner device'):return '1'
            if label.startswith('Name shown'):return 'Küche'
            if label.startswith('MQTT broker'):return 'broker.example'
            if label.startswith('MQTT username'):return '-'
            return default
        with patch('usb_scanner_mqtt.cli.root_required'),patch('usb_scanner_mqtt.cli.restart_if_running'), \
             patch('usb_scanner_mqtt.cli.available_devices',return_value=['/dev/input/by-id/test-event-kbd']), \
             patch('usb_scanner_mqtt.cli.device_name',return_value='Test Scanner'), \
             patch('usb_scanner_mqtt.cli.ask',side_effect=answer),patch('sys.stdout',new_callable=io.StringIO) as output:
            setup(self.path)
        conf=config.load(self.path)
        self.assertFalse(conf['setup_pending']);self.assertTrue(conf['web']['enabled'])
        self.assertEqual(conf['scanner']['name'],'Küche');self.assertEqual(conf['scanner']['layout'],'us')
        self.assertEqual(conf['scanner']['output_profile'],'standard')
        self.assertIn('1. Test Scanner',output.getvalue())

    def test_mqtt_host_rejects_url_and_combined_port(self):
        conf=self.browser_setup();conf['scanner']['device']='/dev/input/test';conf['setup_pending']=False
        for host in ('http://broker','https://broker','mqtt://broker','broker:1883','bad host'):
            conf['mqtt']['host']=host
            with self.assertRaises(ValueError):config.validate(conf)
        for host in ('broker.example','192.0.2.5','::1'):
            conf['mqtt']['host']=host;config.validate(conf)

    def test_old_config_migration_is_not_pending(self):
        conf=config.defaults();del conf['setup_pending']
        conf['mqtt']['host']='broker.example';conf['scanner']['device']='/dev/input/test'
        self.assertFalse(config.validate(conf)['setup_pending'])


class MaintenanceTests(unittest.TestCase):
    def test_ipv4_filter_sort_and_bind_addresses(self):
        with patch('usb_scanner_mqtt.maintenance.subprocess.run',return_value=Mock(returncode=0,stdout='192.0.2.20 127.0.0.1 ::1 192.0.2.2 192.0.2.20 0.0.0.0 224.0.0.1')):
            self.assertEqual(ipv4_addresses(),['192.0.2.2','192.0.2.20'])
        with patch('usb_scanner_mqtt.maintenance.subprocess.run',side_effect=FileNotFoundError), \
             patch('usb_scanner_mqtt.maintenance.socket.getaddrinfo',return_value=[(None,None,None,None,('192.0.2.3',0))]):
            self.assertEqual(ipv4_addresses(),['192.0.2.3'])
        conf=config.defaults();conf['web']['enabled']=True
        with patch('usb_scanner_mqtt.maintenance.ipv4_addresses',return_value=['192.0.2.4']):
            self.assertEqual(web_urls(conf),['http://192.0.2.4:8765'])
            conf['web']['host']='127.0.0.1';self.assertEqual(web_urls(conf),['http://127.0.0.1:8765'])
        conf['web']['enabled']=False;self.assertEqual(web_urls(conf),[])

    def test_uninstall_retains_or_purges_only_owned_files(self):
        for purge in (False,True):
            with self.subTest(purge=purge),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                owned=['opt/usb-scanner-mqtt/src/app.py','etc/systemd/system/usb-scanner-mqtt.service',
                       'usr/local/bin/myscanner','etc/usb-scanner-mqtt/config.json','var/lib/usb-scanner-mqtt/outbox.sqlite3']
                for name in owned:
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('keep data')
                other=root/'etc/unrelated';other.write_text('unrelated')
                with patch('usb_scanner_mqtt.maintenance.subprocess.run',return_value=Mock(returncode=0)) as run:
                    remove_installation(purge,root)
                self.assertFalse((root/owned[0]).exists());self.assertFalse((root/owned[1]).exists())
                for name in owned[-2:]:self.assertEqual((root/name).exists(),not purge)
                self.assertEqual(other.read_text(),'unrelated')
                calls=[call.args[0] for call in run.call_args_list]
                self.assertEqual(calls[0],['systemctl','is-active','--quiet','usb-scanner-mqtt.service'])
                self.assertIn(['systemctl','stop','usb-scanner-mqtt.service'],calls)
                self.assertFalse(any('apt' in word for call in calls for word in call))

    def test_uninstall_cancellation_and_stop_failure_are_safe(self):
        for answers in (['0'],['1','no'],['2','yes']):
            with patch('builtins.input',side_effect=answers),patch('usb_scanner_mqtt.maintenance.remove_installation') as remove:
                uninstall();remove.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);app=root/'opt/usb-scanner-mqtt';app.mkdir(parents=True)
            with patch('usb_scanner_mqtt.maintenance.subprocess.run',side_effect=[Mock(returncode=0),subprocess.CalledProcessError(1,'stop')]):
                with self.assertRaises(subprocess.CalledProcessError):remove_installation(True,root)
            self.assertTrue(app.is_dir())

    def test_uninstall_confirmation_and_shared_installer_lock(self):
        for answers, purge in ((['1','yes'],False), (['2','DELETE'],True)):
            with patch('builtins.input',side_effect=answers),patch('usb_scanner_mqtt.maintenance.remove_installation') as remove:
                uninstall();remove.assert_called_once_with(purge=purge)
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);lock_path=root/'run/lock/usb-scanner-mqtt.lock'
            lock_path.parent.mkdir(parents=True)
            with lock_path.open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch('usb_scanner_mqtt.maintenance.subprocess.run') as run:
                    with self.assertRaises(ValueError):remove_installation(True,root)
                    run.assert_not_called()

    def test_uninstall_symlinks_are_unlinked_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);outside=root/'unrelated';outside.mkdir();(outside/'data').write_text('safe')
            (root/'opt').mkdir();(root/'opt/usb-scanner-mqtt').symlink_to(outside,target_is_directory=True)
            with patch('usb_scanner_mqtt.maintenance.subprocess.run',return_value=Mock(returncode=4)):
                remove_installation(False,root)
            self.assertEqual((outside/'data').read_text(),'safe')

    def test_cli_uninstall_requires_root_before_any_removal(self):
        with patch('usb_scanner_mqtt.cli.root_required',side_effect=ValueError('root required')), \
             patch('usb_scanner_mqtt.maintenance.uninstall') as remove:
            self.assertEqual(main(['uninstall','--purge']),1);remove.assert_not_called()
