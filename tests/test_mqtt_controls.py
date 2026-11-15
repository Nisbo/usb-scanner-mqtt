"""Stable HA identity and persisted, bounded MQTT control handling without a broker."""
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from usb_scanner_mqtt import config, mqtt_controls as controls
from usb_scanner_mqtt.receiver import Publisher, discovery
from usb_scanner_mqtt.web import Dashboard


class MQTTControlsTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'config.json'
        self.conf=config.defaults();self.conf['mqtt']['host']='broker.example';self.conf['scanner']['device']='/dev/input/test'
        config.save(self.conf,self.path)
        self.publisher=Publisher.__new__(Publisher)
        self.publisher.stop=threading.Event()
        self.publisher.config=self.conf;self.publisher.client=Mock();self.publisher.connected=threading.Event();self.publisher.connected.set()
        self.publisher.control_lock=threading.Lock();self.publisher.pending_controls={}
        self.publisher.scan_gate=threading.RLock();self.publisher.test_paused=threading.Event();self.publisher.device_connected=threading.Event()
        self.publisher.availability=controls.base_topic(self.conf)+'/availability'
        self.publisher.service_availability=controls.base_topic(self.conf)+'/status/availability'
        self.changed=Mock()
        self.dashboard=Dashboard(self.conf,self.path,self.publisher,Mock(count=lambda:0),Mock(),control_changed=self.changed)
        self.addCleanup(self.dashboard.end_test)
        self.publisher.control=self.dashboard.set_control

    def command(self,key,payload=b'ON',retained=False):
        self.publisher.on_message(None,None,SimpleNamespace(topic=controls.control_topic(self.conf,key,'set'),payload=payload,retain=retained))

    def test_new_install_machine_name_and_legacy_random_id_do_not_change_identity(self):
        first=discovery(self.conf);switches=controls.discovery(self.conf)
        fresh=config.defaults();fresh['scanner']['id']=self.conf['scanner']['id']
        fresh['scanner']['name']='Completely different name';fresh['installation_id']='different old value'
        second=discovery(fresh)
        self.assertEqual(first[0],second[0]);self.assertEqual(first[1]['unique_id'],second[1]['unique_id'])
        self.assertEqual(first[1]['default_entity_id'],'sensor.usb_scanner_mqtt_usb_scanner_1_last_scan')
        self.assertEqual(first[1]['device']['identifiers'],second[1]['device']['identifiers'])
        for (_,a),(_,b) in zip(switches,controls.discovery(fresh)):
            self.assertEqual(a['unique_id'],b['unique_id']);self.assertEqual(a['default_entity_id'],b['default_entity_id'])
        fresh['scanner']['id']='other-scanner'
        self.assertNotEqual(discovery(fresh)[1]['unique_id'],first[1]['unique_id'])
        self.assertNotIn('installation_id',config.defaults())

    def test_three_switches_share_device_and_confirm_states_without_retained_commands(self):
        sensor=discovery(self.conf)[1]
        switches=controls.discovery(self.conf)
        self.assertEqual(len(switches),3)
        self.assertEqual(len({payload['unique_id'] for _,payload in switches}),3)
        for topic,payload in switches:
            self.assertIn('/switch/',topic);self.assertFalse(payload['retain']);self.assertFalse(payload['optimistic'])
            self.assertEqual(payload['device']['identifiers'],sensor['device']['identifiers'])
            self.assertNotEqual(payload['command_topic'],payload['state_topic'])
            self.assertEqual(payload['availability_topic'],self.publisher.service_availability)
        self.assertEqual(sensor['availability_mode'],'all')
        self.assertEqual({item['topic'] for item in sensor['availability']},{self.publisher.availability,self.publisher.service_availability})

    def test_network_callback_does_not_write_config_and_commands_are_coalesced(self):
        before=self.path.read_bytes()
        self.command('scan_forwarding',b'OFF');self.command('scan_forwarding',b'ON');self.command('scan_forwarding',b'OFF')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.publisher.pending_controls,{'scan_forwarding':False})
        self.publisher.process_controls()
        self.assertFalse(config.load(self.path)['scan_send_enabled']);self.assertFalse(self.conf['scan_send_enabled'])
        self.assertFalse(self.dashboard.snapshot()['send_enabled'])
        self.assertEqual(self.publisher.pending_controls,{})
        self.assertTrue(all(call.kwargs['retain'] for call in self.publisher.client.publish.call_args_list))
        self.assertIn(((controls.control_topic(self.conf,'scan_forwarding','state'),'OFF'),{'qos':1,'retain':True}),[(c.args,c.kwargs) for c in self.publisher.client.publish.call_args_list])

    def test_all_flags_persist_and_live_product_worker_is_notified_without_logout(self):
        self.dashboard.config['web']['auth_enabled']=False
        token=self.dashboard.token
        for key in controls.CONTROLS:
            self.command(key,b'OFF');self.publisher.process_controls()
            self.assertFalse(controls.values(config.load(self.path))[key])
            self.command(key,b'ON');self.publisher.process_controls()
            self.assertTrue(controls.values(config.load(self.path))[key])
        self.assertEqual(self.changed.call_count,6)
        self.assertEqual(self.dashboard.token,token)
        self.dashboard.reload.assert_not_called()

    def test_invalid_retained_or_unknown_commands_are_ignored_and_memory_is_bounded(self):
        before=self.path.read_bytes()
        for payload in (b'on',b'1',b'',b'online',b'{"enabled":true}',b'X'*65536):self.command('open_facts',payload)
        self.command('open_facts',b'ON',retained=True)
        self.command('unknown')
        self.assertEqual(self.publisher.pending_controls,{})
        self.publisher.process_controls();self.assertEqual(self.path.read_bytes(),before)
        for _ in range(100):
            for key in controls.CONTROLS:self.command(key)
        self.assertEqual(len(self.publisher.pending_controls),3)

    def test_failed_disk_save_leaves_runtime_and_announced_state_unchanged(self):
        before=self.path.read_bytes()
        self.command('scan_forwarding',b'OFF')
        with patch('usb_scanner_mqtt.web.settings.save',side_effect=OSError('test')),self.assertLogs('usb_scanner_mqtt.receiver',level='WARNING'):
            self.publisher.process_controls()
        self.assertEqual(self.path.read_bytes(),before)
        self.assertTrue(self.conf['scan_send_enabled'])
        self.changed.assert_not_called()
        self.assertEqual(self.publisher.client.publish.call_args_list[0].args[1],'ON')

    def test_commands_do_not_cancel_local_capture_or_overwrite_auth_or_other_settings(self):
        self.dashboard.begin_scanning()
        saved=config.load(self.path);saved['scanner']['name']='New name';saved['mqtt']['password']='test-password';config.save(saved,self.path)
        self.command('scan_forwarding',b'ON');self.publisher.process_controls()
        self.assertTrue(self.publisher.test_paused.is_set())
        self.assertTrue(self.dashboard.snapshot()['scan_active'])
        loaded=config.load(self.path)
        self.assertEqual(loaded['scanner']['name'],'New name');self.assertEqual(loaded['mqtt']['password'],'test-password')
        for key,value in (('unsupported',True),('open_facts','ON')):
            with self.assertRaises(ValueError):self.dashboard.set_control(key,value)

    def test_shutdown_does_not_reannounce_online_or_accept_more_commands(self):
        self.publisher.stop.set()
        self.publisher.announce()
        self.publisher.on_message(None,None,SimpleNamespace(topic='homeassistant/status',payload=b'online',retain=False))
        self.command('open_facts')
        self.publisher.client.publish.assert_not_called()
        self.assertEqual(self.publisher.pending_controls,{})

    def test_ha_birth_republishes_all_discovery_and_states_only_on_birth_topic(self):
        self.publisher.announce()
        calls=self.publisher.client.publish.call_args_list
        self.assertEqual(len(calls),12)
        self.assertEqual(sum('/config' in c.args[0] for c in calls),7)
        self.assertTrue(all(c.kwargs['retain'] for c in calls))
        self.publisher.client.publish.reset_mock()
        self.publisher.on_message(None,None,SimpleNamespace(topic='arbitrary/topic',payload=b'online',retain=False))
        self.publisher.client.publish.assert_not_called()
        self.publisher.on_message(None,None,SimpleNamespace(topic='homeassistant/status',payload=b'online',retain=False))
        self.assertEqual(self.publisher.client.publish.call_count,12)


if __name__=='__main__':unittest.main()
