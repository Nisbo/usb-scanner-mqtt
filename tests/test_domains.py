"""Strict host policy, independent of optional dashboard authentication."""
import copy
import tempfile
from pathlib import Path
import unittest
from usb_scanner_mqtt import config


class DomainTests(unittest.TestCase):
    def conf(self):
        value=config.defaults();value['setup_pending']=True;value['web']['enabled']=True
        return config.validate(value)

    def test_defaults_are_ip_only_including_upgrades(self):
        conf=self.conf();web=conf['web']
        self.assertFalse(web['domain_access']);self.assertEqual(web['allowed_domains'],[])
        for host in ('localhost','scanner.local','scanner.example','evil.example'):
            self.assertFalse(config.host_allowed(host,web,'127.0.0.1'))
        self.assertTrue(config.host_allowed('127.0.0.1',web,'127.0.0.1'))
        self.assertFalse(config.host_allowed('192.0.2.5',web,'127.0.0.1'))
        self.assertTrue(config.host_allowed('::1',web,'::1'))

    def test_exact_domains_do_not_allow_subdomains_or_siblings(self):
        web={'domain_access':True,'allowed_domains':['domain.de','sub.domain.de']}
        for host in ('domain.de','sub.domain.de','DOMAIN.DE'):
            self.assertTrue(config.host_allowed(host,web,'127.0.0.1'))
        for host in ('a.domain.de','domain.de.evil.test','evildomain.de','sub.sub.domain.de'):
            self.assertFalse(config.host_allowed(host,web,'127.0.0.1'))
        web['domain_access']=False
        self.assertFalse(config.host_allowed('domain.de',web,'127.0.0.1'))
        web.update(domain_access=True,allowed_domains=[])
        self.assertFalse(config.host_allowed('domain.de',web,'127.0.0.1'))

    def test_normalization_persistence_and_disabled_list(self):
        value=self.conf();value['web'].update(domain_access=False,allowed_domains=[' DOMAIN.DE ','domain.de','BÜCHER.de'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json';config.save(value,path);loaded=config.load(path)
        self.assertEqual(loaded['web']['allowed_domains'],['domain.de','xn--bcher-kva.de'])
        self.assertFalse(loaded['web']['domain_access'])

    def test_invalid_settings_never_replace_saved_configuration(self):
        good=self.conf()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json';config.save(good,path);before=path.read_bytes()
            for domains in ('domain.de',[None],['https://domain.de'],['domain.de:443'],['domain.de/path'],['*.domain.de'],['127.0.0.1'],['localhost'],['bad..de'],['-bad.de'],['bad.de@evil.test'],['bad.de\nother.de'],['x.de']*101):
                broken=copy.deepcopy(good);broken['web']['allowed_domains']=domains
                with self.subTest(domains=domains),self.assertRaises(ValueError):config.save(broken,path)
                self.assertEqual(path.read_bytes(),before)
            broken=copy.deepcopy(good);broken['web']['domain_access']='true'
            with self.assertRaises(ValueError):config.save(broken,path)
