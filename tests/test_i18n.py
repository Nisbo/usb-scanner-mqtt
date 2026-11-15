"""Translation coverage for initial UI text; user data must not be translated."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest

STATIC = Path(__file__).resolve().parents[1] / 'src/usb_scanner_mqtt/static'


class TextCollector(HTMLParser):
    def __init__(self):
        super().__init__(); self.texts=[]; self.excluded=0
    def handle_starttag(self, tag, attrs):
        if tag in ('code','textarea','pre'):self.excluded+=1
        for name,value in attrs:
            if name in ('title','aria-label','placeholder'):self.texts.append(value)
    def handle_endtag(self, tag):
        if tag in ('code','textarea','pre'):self.excluded-=1
    def handle_data(self, data):
        if not self.excluded and data.strip():self.texts.append(data.strip())


class TranslationTests(unittest.TestCase):
    def test_all_initial_ui_text_has_english_translation(self):
        source=(STATIC/'i18n.js').read_text()
        messages=json.loads(re.search(r'const messages = (\{.*?\});\n  let saved;',source,re.S)[1])
        parser=TextCollector();parser.feed((STATIC/'index.html').read_text())
        unchanged={'USB 2 MQTT Scanner','☾',' · ','·','Status','Scanner','MQTT & Home Assistant','Broker','Port','.','English'}
        self.assertEqual(sorted(set(parser.texts)-set(messages)-unchanged),[])
        self.assertTrue(all(isinstance(value,str) and value for value in messages.values()))
        self.assertIn('pre, textarea, code',source)
        self.assertIn('localStorage',source)
