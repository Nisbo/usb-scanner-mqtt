import unittest
from usb_scanner_mqtt.diagnostics import diagnose_scan


def alt_digits(digits, release=True):
    codes = dict(zip('0123456789', (82,79,80,81,75,76,77,71,72,73)))
    events = [[56,1]]
    for digit in digits:
        events += [[codes[digit],1], [codes[digit],2], [codes[digit],0]]
    if release:
        events += [[56,0]]
    return events


class DiagnosticsTests(unittest.TestCase):
    def test_alt_digits_keep_zeroes_repeats_ignored_and_prefix_is_not_complete_scan(self):
        events = [[2,1],[2,0]] + alt_digits('00196') + [[28,1]]
        result = diagnose_scan(events)
        self.assertEqual(result['alt_sequences'], [
            {'digits':'00196', 'other_keys':[], 'complete':True, 'start_event':2}])
        for error in result['first_error'].values():
            self.assertEqual(error['prefix'], '1')
            self.assertEqual(error['keycode'], 82)
            self.assertEqual(error['modifiers'], [56])

    def test_multiple_unfinished_and_non_digit_alt_sequences(self):
        events = alt_digits('0142') + [[56,1],[30,1],[30,0],[79,1]]
        result = diagnose_scan(events)['alt_sequences']
        self.assertEqual([item['digits'] for item in result], ['0142','1'])
        self.assertEqual([item['complete'] for item in result], [True,False])
        self.assertEqual(result[1]['other_keys'], [30])

    def test_altgr_is_not_a_left_alt_code_and_invalid_layout_is_reported(self):
        result = diagnose_scan([[100,1],[16,1],[16,0],[100,0],[28,1]])
        self.assertEqual(result['alt_sequences'], [])
        self.assertIsNone(result['first_error']['de'])
        self.assertEqual(result['first_error']['us']['keycode'], 16)

    def test_valid_scan_and_terminator_only_have_no_errors(self):
        for events in ([[28,1]], [[2,1],[2,0],[28,1]]):
            result = diagnose_scan(events)
            self.assertEqual(result, {'alt_sequences':[], 'first_error':{'us':None,'de':None}})
