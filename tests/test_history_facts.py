"""Durable scan history and product enrichment, without external HTTP services."""
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from usb_scanner_mqtt import config
from usb_scanner_mqtt.open_facts import Enricher, Lookup, RequestBudget, parse_product, product_image_url
from usb_scanner_mqtt.receiver import Outbox, scan_payload
from usb_scanner_mqtt.web import Dashboard

OPTIONS = dict(enabled=True, include_mqtt=True, language='de', timeout=1)
DATA = dict(name='Limo', brand='Marke', package_quantity='1,25 l', image_url=None, product_type='food', source='Open Food Facts')


class HistoryFactsTests(unittest.TestCase):
    def setUp(self):
        budget=patch('usb_scanner_mqtt.open_facts._BUDGET',RequestBudget());budget.start();self.addCleanup(budget.stop)
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'outbox.db'
        self.store = Outbox(self.path, history_limit=3)
        self.addCleanup(lambda: self.store.close())

    def test_old_outbox_migrates_and_existing_payload_and_id_survive(self):
        self.store.close()
        self.path.unlink()
        db=sqlite3.connect(self.path)
        db.execute('CREATE TABLE outbox (sequence INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload TEXT NOT NULL)')
        payload=scan_payload('00123','scanner')
        db.execute('INSERT INTO outbox(topic,payload) VALUES (?,?)',('old/topic',json.dumps(payload)));db.commit();db.close()
        self.store=Outbox(self.path)
        self.assertEqual(json.loads(self.store.first()[2]),payload)
        self.assertEqual(self.store.first()[1],'old/topic')
        self.assertEqual(self.store.history(),[])

    def test_modes_limit_persistence_ids_and_sent_status(self):
        payloads=[scan_payload('00123','scanner') for _ in range(4)]
        self.store.record(payloads[0],'local')
        self.store.record(payloads[1],'disabled')
        self.store.put('scan',payloads[2],record=True)
        self.store.record(payloads[3],'local')
        self.assertEqual([row['status'] for row in self.store.history()],['disabled','queued','local'])
        self.assertEqual(len({p['scan_id'] for p in payloads}),4)
        self.store.remove(self.store.first()[0])
        self.store.close();self.store=Outbox(self.path,3)
        self.assertEqual([row['status'] for row in self.store.history()],['disabled','sent','local'])
        self.assertTrue(all(row['text']=='00123' for row in self.store.history()))
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        self.assertEqual(len(self.store.history(limit=1,offset=1)),1)

    def test_durable_job_finishes_once_in_original_message_after_history_deleted(self):
        payload=scan_payload('00123','scanner')
        self.store.put('original/topic',payload,OPTIONS,record=True)
        self.assertIsNone(self.store.first())
        self.store.clear_history()
        self.assertEqual(self.store.count(),1)
        self.store.close();self.store=Outbox(self.path)
        lookup=Mock();lookup.lookup.return_value=('found',DATA,False)
        worker=Enricher(self.store,lookup)
        self.assertTrue(worker.process());self.assertFalse(worker.process())
        row=self.store.first();message=json.loads(row[2])
        self.assertEqual(row[1],'original/topic')
        self.assertEqual({key:message[key] for key in payload},payload)
        self.assertEqual(message['off_data'],DATA);self.assertEqual(message['off_status'],'found')
        lookup.lookup.assert_called_once_with('00123','de',1)
        self.store.close();self.store=Outbox(self.path)
        self.assertEqual(self.store.first()[2],row[2])
        self.assertEqual(self.store.history(),[])

    def test_local_and_gui_only_product_data_never_send_an_extra_message(self):
        local=scan_payload('00123','scanner');live=scan_payload('00123','scanner')
        self.store.record(local,'local',OPTIONS)
        self.store.put('scan',live,{**OPTIONS,'include_mqtt':False},record=True)
        self.assertEqual(json.loads(self.store.first()[2]),live)
        worker=Enricher(self.store,Mock(lookup=Mock(return_value=('found',DATA,True))))
        self.assertTrue(worker.process());self.assertTrue(worker.process());self.assertFalse(worker.process())
        self.assertEqual(self.store.count(),1)
        self.assertEqual(json.loads(self.store.first()[2]),live)
        self.assertTrue(all(row['off_data']==DATA for row in self.store.history()))
        self.assertTrue(all(row['off_cached'] for row in self.store.history()))

    def test_disabling_lookup_resolves_pending_work_without_network(self):
        payload=scan_payload('00123','scanner')
        self.store.put('scan',payload,OPTIONS,record=True)
        lookup=Mock()
        self.assertTrue(Enricher(self.store,lookup,enabled=False).process())
        lookup.lookup.assert_not_called()
        self.assertEqual(json.loads(self.store.first()[2])['off_status'],'disabled')

    def test_lower_history_limit_keeps_all_pending_mqtt_jobs(self):
        for number in range(5):
            self.store.put('scan',scan_payload('0012'+str(number),'scanner'),OPTIONS,record=True)
        self.assertEqual(self.store.history_count(),3)
        self.store.close();self.store=Outbox(self.path,1)
        self.assertEqual(self.store.history_count(),1);self.assertEqual(self.store.count(),5)
        worker=Enricher(self.store,Mock(lookup=Mock(return_value=('not_found',None,False))))
        self.assertEqual(sum(worker.process() for _ in range(6)),5)
        for _ in range(5):self.store.remove(self.store.first()[0])
        self.assertEqual(self.store.count(),0)

    def test_error_timeout_not_found_and_non_product_still_release_mqtt(self):
        for status in ('error','timeout','not_found','not_applicable','rate_limited','unavailable'):
            payload=scan_payload('https://example.invalid/','scanner')
            self.store.put('scan',payload,OPTIONS,record=True)
            Enricher(self.store,Mock(lookup=Mock(return_value=(status,None,False)))).process()
            row=self.store.first();message=json.loads(row[2])
            self.assertEqual(message['ean'],payload['ean'])
            self.assertEqual(message['off_status'],status);self.assertIsNone(message['off_data'])
            self.store.remove(row[0])

    def test_cache_is_persistent_language_specific_and_expires(self):
        self.store.cache('00123','de','found',DATA,60)
        self.store.cache('00123','en','not_found',None,60)
        self.store.close();self.store=Outbox(self.path)
        fetch=Mock();lookup=Lookup(self.store,fetch)
        self.assertEqual(lookup.lookup('00123','de',1),('found',DATA,True))
        self.assertEqual(lookup.lookup('00123','en',1),('not_found',None,True))
        fetch.assert_not_called()
        with patch('usb_scanner_mqtt.storage.time.time',return_value=time.time()+61):
            self.assertIsNone(self.store.cached('00123','de'))
        self.store.clear_cache();self.assertIsNone(self.store.cached('00123','en'))

    def test_bursts_use_sliding_minute_window_and_cache_bypasses_limit(self):
        fetch=Mock(return_value=('not_found',None));lookup=Lookup(self.store,fetch)
        with patch('usb_scanner_mqtt.open_facts.time.monotonic',return_value=1000) as clock:
            for number in range(10):
                self.assertEqual(lookup.lookup(f'{number:05d}','de',1)[0],'not_found')
            clock.return_value=1010
            for number in range(10,15):
                self.assertEqual(lookup.lookup(f'{number:05d}','de',1)[0],'not_found')
            self.assertEqual(fetch.call_count,15)
            self.assertEqual(lookup.lookup('00124','de',1)[0],'local_rate_limited')
            self.assertEqual(lookup.lookup('00000','de',1),('not_found',None,True))
            clock.return_value=1059.99
            self.assertEqual(lookup.lookup('00124','de',1)[0],'local_rate_limited')
            clock.return_value=1060
            for number in range(20,30):
                self.assertEqual(lookup.lookup(f'{number:05d}','de',1)[0],'not_found')
            self.assertEqual(lookup.lookup('00124','de',1)[0],'local_rate_limited')
            clock.return_value=1070
            self.assertEqual(lookup.lookup('00124','de',1)[0],'not_found')

    def test_error_cooldown_is_distinct_from_server_and_local_rate_limits(self):
        fetch=Mock(return_value=('error',None));lookup=Lookup(self.store,fetch)
        with patch('usb_scanner_mqtt.open_facts.time.monotonic',return_value=1000) as clock:
            self.assertEqual(lookup.lookup('00123','de',1)[0],'error')
            self.assertEqual(lookup.lookup('00124','de',1)[0],'cooldown')
            self.assertEqual(fetch.call_count,1)
            self.assertIsNone(self.store.cached('00123','de'))
            clock.return_value=1060;fetch.return_value=('server_rate_limited',None)
            self.assertEqual(lookup.lookup('00124','de',1)[0],'server_rate_limited')
            self.assertEqual(lookup.lookup('00125','de',1)[0],'server_rate_limited')
            self.assertEqual(fetch.call_count,2)

    def test_slow_or_hung_network_has_one_thread_and_bounded_wait(self):
        release=threading.Event()
        def fetch(*args):
            release.wait(3);return 'not_found',None
        lookup=Lookup(self.store,fetch)
        start=time.monotonic()
        self.assertEqual(lookup.lookup('00123','de',.03)[0],'timeout')
        self.assertLess(time.monotonic()-start,.5)
        lookup.next_request=0
        self.assertEqual(lookup.lookup('00124','de',.03)[0],'unavailable')
        release.set()

    def test_http_budget_and_busy_gate_survive_lookup_recreation(self):
        first=Lookup(self.store,Mock())
        first.next_request=time.monotonic()+60
        second=Lookup(self.store,Mock())
        self.assertEqual(second.lookup('00123','de',1)[0],'cooldown')
        first.next_request=0
        first.busy.acquire()
        try:
            self.assertEqual(second.lookup('00123','de',1)[0],'unavailable')
            second.fetch.assert_not_called()
        finally:
            first.busy.release()

    def test_arbitrary_qr_and_unicode_numbers_are_not_queried(self):
        fetch=Mock();lookup=Lookup(self.store,fetch)
        for code in ('https://example.com','test', '１２３４', '123', '1'*33, None):
            self.assertEqual(lookup.lookup(code,'de',1)[0],'not_applicable')
        fetch.assert_not_called()

    def test_product_parsing_language_nonfood_quantity_and_untrusted_text(self):
        self.assertEqual(parse_product({'product_name_de':' Creme &amp; Öl ','product_name_en':'Cream','brands':' Test, Other',
            'product_quantity':1.25,'product_quantity_unit':'L','image_front_thumb_url':'javascript:bad','product_type':'beauty'},'de'),
            dict(name='Creme & Öl',brand='Test',package_quantity='1,25 l',image_url=None,product_type='beauty',source='Open Food Facts'))
        self.assertIsNone(parse_product({'product_name':34},'de'))
        self.assertIsNone(parse_product([], 'de'))
        self.assertEqual(parse_product({'product_name_en':'Fallback','quantity':'unknown'},'fr')['name'],'Fallback')

    def test_large_images_upgrade_old_thumbnails_and_prefer_requested_language(self):
        base='https://images.openfoodfacts.org/images/products/123/456/789/0000/'
        self.assertEqual(product_image_url(base+'front_de.7.100.jpg'),base+'front_de.7.full.jpg')
        data=parse_product({'product_name':'Test','image_front_url':base+'front_en.6.400.jpg',
            'selected_images':{'front':{'display':{'de':base+'front_de.7.400.jpg'}}}},'de')
        self.assertEqual(data['image_url'],base+'front_de.7.full.jpg')
        for bad in ('https://evil.example/image.jpg','javascript:alert(1)','https://[invalid','https://images.openfoodfacts.org:1234/a.jpg'):
            self.assertIsNone(product_image_url(bad))
        self.store.cache('00123','de','found',{**DATA,'image_url':base+'front_de.7.100.jpg','package_quantity':'1unknown'},60)
        cached=Lookup(self.store,Mock()).lookup('00123','de',1)[1]
        self.assertEqual(cached['image_url'],base+'front_de.7.full.jpg');self.assertIsNone(cached['package_quantity'])
        payload=scan_payload('00123','scanner');self.store.record(payload,'local',OPTIONS)
        self.store.finish_job(payload['scan_id'],'found',{**DATA,'image_url':base+'front_de.7.100.jpg','package_quantity':'1unknown'})
        self.assertEqual(self.store.history()[0]['off_data']['image_url'],base+'front_de.7.full.jpg')
        self.assertIsNone(self.store.history()[0]['off_data']['package_quantity'])

    def test_unknown_quantity_is_not_displayed_as_a_package_size(self):
        for quantity in ('unknown','1unknown','1 Unknown','UNKNOWN 1'):
            self.assertIsNone(parse_product({'product_name':'Test','quantity':quantity},'de')['package_quantity'])
        self.assertIsNone(parse_product({'product_name':'Test','product_quantity':1,'product_quantity_unit':'unknown'},'de')['package_quantity'])
        self.assertEqual(parse_product({'product_name':'Test','quantity':'1L'},'de')['package_quantity'],'1 l')

    def test_request_uses_v3_all_types_fields_and_user_agent_without_v2_status(self):
        response=Mock();response.read.return_value=json.dumps({'product':{'product_name_de':'Test'}}).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch('urllib.request.urlopen',return_value=response) as request:
            self.assertEqual(Lookup.request('00123','de',1)[0],'found')
            url=request.call_args.args[0].full_url
            self.assertIn('/api/v3/product/00123.json?',url);self.assertIn('product_type=all',url)
            self.assertIn('product_name_de',url)
            self.assertIn('usb-scanner-mqtt/',request.call_args.args[0].get_header('User-agent'))
        for error in (TimeoutError(), urllib.error.URLError(TimeoutError())):
            with patch('urllib.request.urlopen',side_effect=error):
                self.assertEqual(Lookup.request('00123','de',1),('timeout',None))
        for code,status in ((404,'not_found'),(429,'server_rate_limited'),(503,'error')):
            with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('https://example.invalid',code,'',{},None)):
                self.assertEqual(Lookup.request('00123','de',1),(status,None))

    def test_invalid_response_is_not_a_cached_missing_product(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        for raw in (b'[]',b'bad json',b'x'*(512*1024+1)):
            response.read.return_value=raw
            with patch('urllib.request.urlopen',return_value=response):
                self.assertEqual(Lookup.request('00123','de',1),('error',None))

    def test_local_dashboard_history_survives_recreation_and_calibration_excluded(self):
        conf=config.defaults();publisher=Mock();publisher.scan_gate=threading.RLock();publisher.test_paused=threading.Event()
        dashboard=Dashboard(conf,None,publisher,self.store,Mock(),history=self.store)
        self.addCleanup(dashboard.end_test)
        dashboard.begin_scanning()
        for code,value in ((2,1),(2,0),(28,1)):
            dashboard.observe(code,value)
        self.assertEqual(dashboard.snapshot()['scan_items'][0]['text'],'1')
        self.assertEqual(self.store.count(),0)
        dashboard.end_test();dashboard=Dashboard(conf,None,publisher,self.store,Mock(),history=self.store)
        self.addCleanup(dashboard.end_test)
        self.assertEqual(dashboard.snapshot()['scan_items'][0]['status'],'local')
        dashboard.begin_test(expected='1')
        for code,value in ((2,1),(2,0),(28,1)):
            dashboard.observe(code,value)
        self.assertEqual(self.store.history_count(),1)
        dashboard.clear_scans(self.store.history()[0]['id']);self.assertEqual(self.store.history_count(),0)

    def test_new_options_migrate_and_validate(self):
        conf=config.defaults();conf['mqtt']['host']='broker';conf['scanner']['device']='/dev/input/test'
        del conf['open_facts'];del conf['history'];config.validate(conf)
        self.assertFalse(conf['open_facts']['enabled']);self.assertEqual(conf['history']['limit'],1000)
        for key,value in (('timeout',0),('timeout',float('nan')),('timeout',True),('language','xx'),('enabled',1)):
            broken=json.loads(json.dumps(conf));broken['open_facts'][key]=value
            with self.assertRaises(ValueError):config.validate(broken)


if __name__=='__main__':
    unittest.main()
