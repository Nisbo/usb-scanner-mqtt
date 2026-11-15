"""Installer language must affect prompts, never scanned or configured values."""
import io
import os
import unittest
from unittest.mock import patch

from usb_scanner_mqtt.maintenance import uninstall, print_web_addresses
from usb_scanner_mqtt.terminal_i18n import text
from usb_scanner_mqtt.config import defaults


class TerminalLanguageTests(unittest.TestCase):
    def test_default_fallback_and_german_do_not_change_unknown_text(self):
        for language in ('', 'fr', 'de'):
            with patch.dict(os.environ, {'USB_SCANNER_INSTALL_LANGUAGE': language}):
                self.assertEqual(text('ÖöÄäÜüß123ABc'), 'ÖöÄäÜüß123ABc')
                self.assertEqual(text('Choice [1]: '), 'Auswahl [1]: ' if language == 'de' else 'Choice [1]: ')

    def test_german_uninstall_requires_displayed_confirmation(self):
        with patch.dict(os.environ, {'USB_SCANNER_INSTALL_LANGUAGE': 'de'}), \
             patch('usb_scanner_mqtt.maintenance.remove_installation') as remove, \
             patch('builtins.input', side_effect=['1', 'ja']) as ask, \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            uninstall()
            self.assertIn('Einstellungen und wartende Scans behalten', output.getvalue())
            self.assertEqual(ask.call_args.args[0], 'Zum Bestätigen ja eingeben: ')
            remove.assert_called_once_with(purge=False)

    def test_german_purge_keeps_explicit_delete_token(self):
        with patch.dict(os.environ, {'USB_SCANNER_INSTALL_LANGUAGE': 'de'}), \
             patch('usb_scanner_mqtt.maintenance.remove_installation') as remove, \
             patch('builtins.input', side_effect=['2', 'DELETE']) as ask, \
             patch('sys.stdout', new_callable=io.StringIO):
            uninstall()
            self.assertEqual(ask.call_args.args[0], 'Zum Bestätigen DELETE eingeben: ')
            remove.assert_called_once_with(purge=True)

    def test_browser_link_language_does_not_modify_config_or_url(self):
        config=defaults();config['web']['enabled']=True
        config['web']['host']='192.0.2.10'
        with patch.dict(os.environ, {'USB_SCANNER_INSTALL_LANGUAGE': 'de'}), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            print_web_addresses(config)
            self.assertIn('Öffne einen dieser Links',output.getvalue())
            self.assertIn('http://192.0.2.10:8765',output.getvalue())
            self.assertEqual(config['web']['host'],'192.0.2.10')


if __name__ == '__main__':
    unittest.main()
