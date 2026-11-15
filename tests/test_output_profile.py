import unittest
from usb_scanner_mqtt.keyboard import Decoder
from usb_scanner_mqtt.diagnostics import diagnose_scan
from usb_scanner_mqtt import config


def alt(number):
    codes=dict(zip('0123456789',(82,79,80,81,75,76,77,71,72,73)))
    events=[(69,1),(69,0),(56,1)]
    for digit in str(number):
        events += [(codes[digit],1),(codes[digit],2),(codes[digit],0)]
    return events+[(56,0)]


def decode(events, profile='alt-pair-latin1', **kwargs):
    decoder=Decoder(output_profile=profile, **kwargs)
    results=[]
    for index,(code,value) in enumerate(events):
        result=decoder.feed(code,value,now=index*.001)
        if result is not None: results.append(result)
    return results


class OutputProfileTests(unittest.TestCase):
    def test_pair_with_packed_cr_and_with_separate_enter(self):
        self.assertEqual(decode(alt(50189)), ['Ä'])
        self.assertEqual(decode(alt(50241)+[(28,1)]), ['ÄA'])
        self.assertEqual(decode(alt(50189)+[(28,1)]), ['Ä'])
        self.assertEqual(decode(alt(50189)+alt(50189)), ['Ä','Ä'])
        self.assertEqual(decode(alt(50189), profile='standard'), [])
        self.assertEqual(decode(alt(50241)+[(28,1)], profile='standard'), [])

    def test_multiple_pairs_and_regular_ascii_keep_order(self):
        events=[(2,1),(2,0)]
        for pair in ('ÄÖ','Üä','öü'):
            events += alt(int.from_bytes(pair.encode('latin1'),'big'))
        events += alt(int.from_bytes('ß'.encode('latin1')+b'\r','big'))
        self.assertEqual(decode(events), ['1ÄÖÜäöüß'])
        self.assertEqual(decode([(21,1),(21,0),(28,1)], layout='de'), ['z'])
        self.assertEqual(decode([(21,1),(21,0),(28,1)], layout='us'), ['y'])

    def test_invalid_unfinished_short_control_and_overflow_are_rejected(self):
        for events in (alt(196),alt(65536),alt(0xC400),alt(0xC480),
                       [(56,1),(30,1),(56,0)],alt('123456'),[(56,1),(79,1)]):
            self.assertEqual(decode(events+[(28,1)]), [])
        self.assertEqual(decode(alt(50241)+[(28,1)], max_length=1), [])
        self.assertEqual(decode(alt(50189), max_length=1), ['Ä'])

    def test_timeout_discards_partial_alt_and_recovers_on_next_scan(self):
        decoder=Decoder(output_profile='alt-pair-latin1')
        for code,value in [(56,1),(76,1)]: decoder.feed(code,value,now=1)
        self.assertIsNone(decoder.feed(56,0,now=4))
        self.assertIsNone(decoder.feed(28,1,now=4.1))
        decoder.feed(2,1,now=4.2)
        self.assertEqual(decoder.feed(28,1,now=4.3),'1')

    def test_profile_configuration_migration_and_validation(self):
        conf=config.defaults();conf['mqtt']['host']='localhost';conf['scanner']['device']='/dev/input/test'
        config.validate(conf)
        self.assertEqual(conf['scanner']['output_profile'],'standard')
        conf['scanner']['output_profile']='alt-pair-latin1';config.validate(conf)
        conf['scanner']['output_profile']='guess'
        with self.assertRaises(ValueError):config.validate(conf)

    def test_diagnostics_follow_selected_profile_without_guessing(self):
        events=alt(50241)+[(28,1)]
        self.assertIsNotNone(diagnose_scan(events)['first_error']['us'])
        detail=diagnose_scan(events,'alt-pair-latin1')
        self.assertIsNone(detail['first_error']['us'])
        self.assertEqual(detail['alt_sequences'][0]['digits'],'50241')
