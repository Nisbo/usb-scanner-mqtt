"""Pure product queries must never enter the scanner outbox or history."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from usb_scanner_mqtt import config, mqtt_controls as controls
from usb_scanner_mqtt.manual_lookup import ManualLookup, discovery, topic
from usb_scanner_mqtt.open_facts import Enricher, Lookup
from usb_scanner_mqtt.receiver import Outbox, scan_payload

DATA = dict(name='Testprodukt Ö',brand='Marke',package_quantity='1 l',image_url=None,product_type='food',source='Open Food Facts')


class ManualLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'outbox.db';self.store=Outbox(self.path)
        self.addCleanup(lambda:self.store.close())
        self.conf=config.defaults();self.gateway=ManualLookup(self.conf,self.store)
        self.lookup=Mock();self.lookup.lookup.return_value=('found',DATA,False)
        self.worker=Enricher(self.store,self.lookup,enabled=False)

    def command(self,suffix,payload):self.gateway.accept(topic(self.conf,suffix),payload)

    def test_discovery_entities_and_result_are_separate_from_scans_and_share_device(self):
        entities=discovery(self.conf)
        self.assertEqual([t.split('/')[1] for t,_ in entities],['text','button','sensor'])
        self.assertEqual(len({p['unique_id'] for _,p in entities}),3)
        for _,payload in entities:
            self.assertEqual(payload['device']['identifiers'],[controls.identity(self.conf)])
            self.assertEqual(payload['availability_topic'],controls.base_topic(self.conf)+'/status/availability')
            for field in ('command_topic','state_topic','json_attributes_topic'):
                if field in payload:self.assertNotEqual(payload[field],self.conf['scanner']['topic'])
        self.assertEqual(entities[0][1]['max'],32);self.assertFalse(entities[0][1]['retain'])
        self.assertEqual(entities[1][1]['payload_press'],'LOOKUP');self.assertFalse(entities[1][1]['retain'])
        self.assertIn('value_json.state',entities[2][1]['value_template'])
        self.assertEqual(controls.discovery(self.conf)[1][1]['icon'],'mdi:barcode-scan')

    def test_callback_stages_only_and_input_alone_does_not_start_lookup(self):
        self.command('ean/set',b'0012345')
        self.assertEqual(self.store.manual_snapshot()['ean'],'')
        self.gateway.process()
        self.assertEqual(self.store.manual_snapshot()['ean'],'0012345')
        self.assertIsNone(self.store.manual_job());self.assertFalse(self.worker.process())
        self.lookup.lookup.assert_not_called();self.assertEqual(self.store.count(),0)

    def test_query_with_automatic_lookup_disabled_persists_and_never_becomes_scan(self):
        self.command('ean/set',b'0012345');self.command('start',b'LOOKUP');self.gateway.process()
        pending=self.store.manual_snapshot()['result']
        self.assertEqual(pending['status'],'pending');self.assertNotIn('scan_id',pending)
        self.assertTrue(self.worker.process())
        result=self.store.manual_snapshot()['result']
        self.assertEqual(result['ean'],'0012345');self.assertEqual(result['off_data'],DATA)
        self.assertEqual(result['status'],'found');self.assertEqual(result['state'],'Testprodukt Ö')
        self.lookup.lookup.assert_called_once_with('0012345','en',2)
        self.assertEqual(self.store.count(),0);self.assertEqual(self.store.history_count(),0)
        self.store.close();self.store=Outbox(self.path)
        self.assertEqual(self.store.manual_snapshot()['result'],result)
        self.assertEqual(self.store.manual_snapshot()['ean'],'0012345')

    def test_manual_query_uses_the_same_product_cache_as_scanner_enrichment(self):
        self.store.cache('00123','en','found',DATA,3600)
        fetch=Mock();lookup=Lookup(self.store,fetch)
        worker=Enricher(self.store,lookup,enabled=False)
        self.store.manual_start('00123',self.conf['open_facts'])
        self.assertTrue(worker.process());self.assertTrue(self.store.manual_snapshot()['result']['cached'])
        worker.enabled=True
        self.store.put('scan',scan_payload('00123','scanner'),{**self.conf['open_facts'],'enabled':True},record=True)
        self.assertTrue(worker.process());fetch.assert_not_called()
        self.assertEqual(json.loads(self.store.first()[2])['off_data'],DATA)

    def test_same_ean_can_be_repeated_and_newer_request_wins(self):
        self.store.manual_set_input('00123')
        first=self.store.manual_start('00123',self.conf['open_facts'])
        second=self.store.manual_start('00123',self.conf['open_facts'])
        self.assertNotEqual(first,second)
        self.assertFalse(self.store.manual_finish(first,'found',DATA))
        self.assertEqual(self.store.manual_job()['request_id'],second)
        self.assertTrue(self.store.manual_finish(second,'found',DATA,True))
        self.assertEqual(self.store.manual_snapshot()['result']['request_id'],second)
        self.assertTrue(self.store.manual_snapshot()['result']['cached'])

    def test_ean_is_captured_at_button_press_even_if_input_changes_afterwards(self):
        self.command('ean/set',b'00123');self.command('start',b'LOOKUP');self.command('ean/set',b'00999')
        self.gateway.process()
        self.assertEqual(self.store.manual_snapshot()['ean'],'00999')
        self.assertEqual(self.store.manual_job()['ean'],'00123')
        self.command('start',b'LOOKUP');self.gateway.process()
        self.assertEqual(self.store.manual_job()['ean'],'00999')

    def test_invalid_or_short_input_cannot_trigger_network(self):
        for code in (b'https://example.com',b'ABCD',b'1'*33,'１２３４'.encode()):self.command('ean/set',code)
        self.command('start',b'LOOKUP');self.gateway.process()
        self.assertEqual(self.store.manual_snapshot()['result']['status'],'invalid_input')
        self.command('ean/set',b'123');self.command('start',b'LOOKUP');self.gateway.process()
        self.assertEqual(self.store.manual_snapshot()['result']['status'],'invalid_input')
        self.assertIsNone(self.store.manual_job());self.assertFalse(self.worker.process());self.lookup.lookup.assert_not_called()
        for code in ('abc','1'*33,'https://example.com'):
            with self.assertRaises(ValueError):self.store.manual_start(code,self.conf['open_facts'])

    def test_waiting_work_survives_restart_and_history_clear_does_not_affect_it(self):
        self.store.manual_set_input('00123');request=self.store.manual_start('00123',self.conf['open_facts'])
        self.store.clear_history();self.store.clear_cache();self.store.close();self.store=Outbox(self.path)
        worker=Enricher(self.store,self.lookup,enabled=False)
        self.assertTrue(worker.process());self.assertEqual(self.store.manual_snapshot()['result']['request_id'],request)
        self.assertEqual(self.store.count(),0)

    def test_manual_work_does_not_starve_scanner_jobs(self):
        options={**self.conf['open_facts'],'enabled':True}
        self.store.put('scan',scan_payload('00123','scanner'),options,record=True)
        self.store.manual_start('00123',options)
        self.assertTrue(self.worker.process());self.assertEqual(self.store.manual_snapshot()['result']['status'],'found')
        self.store.manual_start('00124',options)
        self.assertTrue(self.worker.process())
        self.assertIsNotNone(self.store.first())  # Scan released despite the new manual request.
        self.assertEqual(self.store.manual_snapshot()['result']['status'],'pending')
        self.assertTrue(self.worker.process());self.assertEqual(self.store.manual_snapshot()['result']['status'],'found')

    def test_results_and_empty_input_are_retained_without_republishing_scans(self):
        client=Mock();client.publish.return_value=Mock(rc=0)
        self.gateway.publish(client)
        self.assertEqual(client.publish.call_count,2)
        self.assertEqual(json.loads(client.publish.call_args_list[0].args[1]),{'ean':''})
        self.gateway.publish(client);self.assertEqual(client.publish.call_count,2)
        self.store.manual_start('00123',self.conf['open_facts']);self.worker.process();self.gateway.process();self.gateway.publish(client)
        self.assertEqual(client.publish.call_count,4)
        for call in client.publish.call_args_list:
            self.assertTrue(call.kwargs['retain']);self.assertNotEqual(call.args[0],self.conf['scanner']['topic'])
        self.gateway.publish(client,force=True);self.assertEqual(client.publish.call_count,6)
        client.publish.return_value=Mock(rc=4);self.gateway.sent=None
        self.gateway.publish(client);self.assertIsNone(self.gateway.sent)

    def test_newer_queued_requests_are_bounded_and_errors_and_long_names_stay_valid(self):
        for number in range(100):
            self.command('ean/set',f'{number:05d}'.encode());self.command('start',b'LOOKUP')
        self.gateway.process();self.assertEqual(self.store.manual_job()['ean'],'00099')
        for status in ('not_found','timeout','error','local_rate_limited','server_rate_limited','cooldown','unavailable'):
            request=self.store.manual_start('00123',self.conf['open_facts']);self.store.manual_finish(request,status,None)
            result=self.store.manual_snapshot()['result'];self.assertEqual(result['status'],status);self.assertIsNone(result['off_data'])
        request=self.store.manual_start('00123',self.conf['open_facts']);self.store.manual_finish(request,'found',{**DATA,'name':'x'*1000})
        self.assertEqual(len(self.store.manual_snapshot()['result']['state']),255)
        self.assertEqual(len(self.store.manual_snapshot()['result']['off_data']['name']),1000)


if __name__=='__main__':unittest.main()
