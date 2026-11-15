"""Physical-key fixtures for standard national layouts (not real scanner captures)."""
import unittest
from usb_scanner_mqtt.keyboard import Decoder, LAYOUTS
from usb_scanner_mqtt import config
from usb_scanner_mqtt.calibration import compare_candidates


def events(keys):
    result = []
    for key in keys:
        code, modifier = (key, None) if isinstance(key, int) else key
        if modifier: result.append((modifier, 1))
        result.extend(((code, 1), (code, 0)))
        if modifier: result.append((modifier, 0))
    return result


def decode(layout, raw, profile='standard'):
    decoder = Decoder(layout, output_profile=profile)
    return [text for index, (code, value) in enumerate(raw)
            if (text := decoder.feed(code, value, now=index * .001)) is not None]


class LayoutTests(unittest.TestCase):
    def test_national_keys_shift_altgr_and_accents(self):
        fixtures = {
            'gb': ([(3,42),(4,42),(40,42),43,(43,42),86,(86,42),28], '"£@#~\\|'),
            'fr': ([16,30,17,44,39,50,(50,42),3,(3,42),(11,100),
                    26,18,(26,42),22,(39,42),28], 'aqzwm,?é2@êüM'),
            'es': ([39,(39,42),13,(13,42),40,30,(40,42),22,(3,100),(43,100),(40,100),28], 'ñÑ¡¿áü@{}'),
        }
        for layout, (keys, expected) in fixtures.items():
            for profile in ('standard', 'alt-pair-latin1'):
                self.assertEqual(decode(layout, events(keys), profile), [expected], (layout, profile))

    def test_all_layouts_are_detected_from_discriminating_physical_keys(self):
        # Same known punctuation, typed at each layout's physical positions.
        fixtures = {
            'us': [(39,42),53,(13,42),12,(3,42),52,51,39,(2,42),(53,42)],
            'de': [(52,42),(8,42),27,53,(16,100),52,51,(51,42),(2,42),(12,42)],
            'gb': [(39,42),53,(13,42),12,(40,42),52,51,39,(2,42),(53,42)],
            'fr': [52,(52,42),(13,42),7,(11,100),(51,42),50,51,53,(50,42)],
            'es': [(52,42),(8,42),27,53,(3,100),52,51,(51,42),(2,42),(12,42)],
        }
        for layout, keys in fixtures.items():
            from test_output_profile import alt
            for expected_profile in ('standard', 'alt-pair-latin1'):
                raw = events(keys) + (events([28]) if expected_profile == 'standard' else alt(50189))
                expected = ':/+-@.,;!?' + ('' if expected_profile == 'standard' else 'Ä')
                candidates = []
                for candidate in LAYOUTS:
                    for profile in ('standard','alt-pair-latin1'):
                        for text in decode(candidate, raw, profile):
                            candidates.append(dict(layout=candidate, output_profile=profile, text=text))
                result = compare_candidates(candidates, expected, raw)
                self.assertIsNotNone(result['unique'], (layout, result))
                self.assertEqual(result['unique']['layout'], layout)
                self.assertEqual(result['unique']['output_profile'], expected_profile)
            conf=config.defaults(); conf['mqtt']['host']='broker.example'; conf['scanner']['device']='/dev/input/test'; conf['scanner']['layout']=layout; config.validate(conf)

    def test_dead_key_lifecycle_and_invalid_composition(self):
        self.assertEqual(decode('es', events([40,57,28])), ['´'])
        self.assertEqual(decode('fr', events([26,26,28])), ['^'])
        self.assertEqual(decode('es', events([30,40,28])), [])
        self.assertEqual(decode('fr', events([26,2,28])), [])
        self.assertEqual(decode('es', events([40,30,28,48,28])), ['á','b'])
        d=Decoder('es'); d.feed(40,1,now=0)
        d.feed(30,1,now=3)
        self.assertEqual(d.feed(28,1,now=3.1), 'a')
        # Caps affects letters, but does not turn number-row punctuation into digits.
        self.assertEqual(decode('fr', events([58,39,3,28])), ['Mé'])
        self.assertEqual(decode('es', events([58,39,40,30,28])), ['ÑÁ'])
