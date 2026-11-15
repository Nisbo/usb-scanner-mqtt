import unittest
from usb_scanner_mqtt.calibration import BASE, LANGUAGES, compare_candidates
from usb_scanner_mqtt.keyboard import Decoder, LETTERS, US, LAYOUTS


def packed_input(text):
    """Synthetic US-keyboard scanner; Latin-1 non-ASCII bytes use explicit packed Alt pairs."""
    keypad=dict(zip('0123456789',(82,79,80,81,75,76,77,71,72,73)))
    text += '\r'
    events=[]
    index=0
    while index < len(text):
        char=text[index]
        if ord(char)>=160:
            pair=text[index:index+2].encode('latin1')
            if len(pair)!=2:raise AssertionError('synthetic input requires a terminator')
            events.append((56,1))
            for digit in str(int.from_bytes(pair,'big')):events.extend(((keypad[digit],1),(keypad[digit],0)))
            events.append((56,0));index+=2;continue
        if char=='\r':events.extend(((28,1),(28,0)));index+=1;continue
        if char.lower() in LETTERS.values():
            code=next(code for code,value in LETTERS.items() if value==char.lower())
            shift=char.isupper()
        else:
            code,shift=next((code,i==1) for code,pair in US.items() for i,value in enumerate(pair) if value==char)
        if shift:events.append((42,1))
        events.extend(((code,1),(code,0)))
        if shift:events.append((42,0))
        index+=1
    return events


class CalibrationTests(unittest.TestCase):
    def test_language_texts_have_alphabets_digits_and_scope(self):
        self.assertEqual(set(LANGUAGES),{'de','en','fr','es'})
        for test in LANGUAGES.values():
            self.assertIn(BASE,test['text'])
            self.assertEqual(test['text'].encode('latin1').decode('latin1'),test['text'])
            self.assertLess(len(test['text']),1000)
        self.assertIn('ÖöÄäÜüß123ABc',LANGUAGES['de']['text'])
        self.assertIn('Çç',LANGUAGES['fr']['text'])
        self.assertIn('Ññ',LANGUAGES['es']['text'])

    def test_each_language_is_compared_exactly_under_both_output_profiles(self):
        for name,test in LANGUAGES.items():
            events=packed_input(test['text'])
            candidates=[]
            for layout in LAYOUTS:
                for profile in ('standard','alt-pair-latin1'):
                    decoder=Decoder(layout,output_profile=profile)
                    decoded=[]
                    for code,value in events:
                        text=decoder.feed(code,value)
                        if text is not None:decoded.append(text)
                    if len(decoded)==1:candidates.append({'layout':layout,'output_profile':profile,'text':decoded[0]})
            result=compare_candidates(candidates,test['text'],events)
            self.assertEqual(result['unique']['layout'],'us',name)
            self.assertEqual(result['unique']['output_profile'],'standard' if name=='en' else 'alt-pair-latin1',name)

    def test_no_case_space_or_unicode_normalization(self):
        expected='ÖöÄäÜüß123ABc'
        for text in (expected.lower(),expected+' ',expected.replace('Ö','O\u0308')):
            result=compare_candidates([{'layout':'us','output_profile':'standard','text':text}],expected,[])
            self.assertIsNone(result['unique'])
            self.assertIsNotNone(result['difference'])
        self.assertEqual(compare_candidates([{'layout':'us','output_profile':'standard','text':'AB'}],'ABC',[])['difference'],
                         {'position':3,'expected':'C','received':''})

    def test_direct_keys_prefer_standard_but_digits_do_not_identify_layout(self):
        candidates=[{'layout':layout,'output_profile':profile,'text':'123'} for layout in ('us','de') for profile in ('standard','alt-pair-latin1')]
        result=compare_candidates(candidates,'123',[])
        self.assertEqual(len(result['matches']),2)
        self.assertIsNone(result['unique'])
        candidates=[candidate for candidate in candidates if candidate['layout']=='de']
        self.assertEqual(compare_candidates(candidates,'123',[])['unique']['output_profile'],'standard')
