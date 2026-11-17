"""Run installer orchestration in a temporary filesystem with OS commands stubbed.

This does not claim to be a real systemd/apt or USB hardware test.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

from usb_scanner_mqtt import __version__
from usb_scanner_mqtt.config import defaults

ROOT = Path(__file__).resolve().parents[1]


class InstallerTest(unittest.TestCase):
    def test_repeat_update_dependencies_and_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            fakebin = base/'bin'
            fakebin.mkdir()
            logs = base/'commands'
            commit = 'a'*40
            source = base/f'usb-scanner-mqtt-{commit}'
            source.mkdir()
            shutil.copytree(ROOT/'src',source/'src')
            shutil.copy(ROOT/'install.sh',source/'install.sh')
            shutil.copy(ROOT/'usb-scanner-mqtt.service',source/'usb-scanner-mqtt.service')
            (source/'src'/'evdev.py').write_text('')
            (source/'src'/'paho'/'mqtt').mkdir(parents=True)
            for file in ('paho/__init__.py','paho/mqtt/__init__.py','paho/mqtt/client.py'):
                (source/'src'/file).write_text('')
            archive=base/'source.tar.gz'
            with tarfile.open(archive,'w:gz') as output:
                output.add(source,arcname=source.name)
            config_dir=base/'etc'/'usb-scanner-mqtt'
            config_dir.mkdir(parents=True)
            config=defaults()
            config['mqtt'].update(host='broker.local',password='PRIVATE_TEST_PASSWORD')
            config['scanner']['device']='/dev/input/scanner'
            configuration=config_dir/'config.json'
            configuration.write_text(json.dumps(config))
            before=configuration.read_bytes()
            installer=(ROOT/'install.sh').read_text()
            for path in ('/opt/usb-scanner-mqtt','/etc/usb-scanner-mqtt','/var/lib/usb-scanner-mqtt',
                         '/usr/local/bin/myscanner','/etc/systemd/system','/run/lock'):
                installer=installer.replace(path,str(base/path.lstrip('/')))
            path=base/'installer.sh'
            path.write_text(installer)
            (base/'usr/local/bin').mkdir(parents=True)
            (base/'etc/systemd/system').mkdir(parents=True)
            (base/'run/lock').mkdir(parents=True)
            # Use an absolute Python shebang, because python3 itself is stubbed.
            def stub(name,text):
                p=fakebin/name
                p.write_text(f'#!{sys.executable}\n'+text)
                p.chmod(0o755)
            stub('id','print(0)\n')
            stub('uname','print("Linux")\n')
            stub('dpkg-query','import sys\nprint("install ok installed")\n')
            stub('apt-get',f'import sys\nopen({str(logs)!r},"a").write("apt "+" ".join(sys.argv[1:])+"\\n")\n')
            stub('systemctl',f'import sys\nopen({str(logs)!r},"a").write("systemctl "+" ".join(sys.argv[1:])+"\\n")\n')
            stub('sleep','pass\n')
            stub('flock','pass\n')
            stub('curl',f'import sys,shutil\nif "-o" in sys.argv:\n shutil.copyfile({str(archive)!r},sys.argv[sys.argv.index("-o")+1])\nelse:\n print({json.dumps({"sha":commit,"tag_name":"v"+__version__})!r})\n')
            stub('mv','import os,sys\nos.replace(sys.argv[-2],sys.argv[-1])\n')
            stub('python3',f'''import os,sys
if sys.argv[1:3] == ['-m','venv']:
    from pathlib import Path
    p=Path(sys.argv[-1])/'bin'/'python'
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('#!/bin/sh\\nexec {sys.executable} "$@"\\n')
    p.chmod(0o755)
else:
    os.execv({sys.executable!r},[{sys.executable!r}]+sys.argv[1:])
''')
            env={**os.environ,'PATH':str(fakebin)+':'+os.environ['PATH']}
            def run():
                result=subprocess.run(['bash',str(path),'--update'],env=env,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertNotIn('PRIVATE_TEST_PASSWORD',result.stdout+result.stderr)
            run()
            run()
            self.assertEqual(configuration.read_bytes(),before)
            self.assertEqual(len(list((base/'opt/usb-scanner-mqtt/releases').iterdir())),1)
            self.assertNotIn('apt ',logs.read_text())
            self.assertEqual(logs.read_text().count('systemctl restart'),2)
            self.assertTrue((base/'usr/local/bin/myscanner').is_file())
            self.assertTrue((base/'etc/systemd/system/usb-scanner-mqtt.service').is_file())
            # Repair a missing file even when the published commit is unchanged.
            current = (base/'opt/usb-scanner-mqtt/current').resolve()
            (current/'src/usb_scanner_mqtt/receiver.py').unlink()
            run()
            repaired = (base/'opt/usb-scanner-mqtt/current').resolve()
            self.assertNotEqual(current, repaired)
            self.assertTrue((repaired/'src/usb_scanner_mqtt/receiver.py').is_file())
            self.assertEqual(configuration.read_bytes(), before)
            # Repair one missing distro dependency; do not reinstall every package.
            stub('dpkg-query','import sys\nprint("missing" if sys.argv[-1] == "python3-evdev" else "install ok installed")\n')
            run()
            self.assertIn('apt install -y --no-install-recommends python3-evdev',logs.read_text())
            self.assertEqual(configuration.read_bytes(),before)
            # An older source version must never replace the installed build.
            stub('dpkg-query', 'print("install ok installed")\n')
            version_file = source/'src/usb_scanner_mqtt/__init__.py'
            original_version = version_file.read_text()
            version_file.write_text(original_version.replace(__version__, '0.12.0'))
            with tarfile.open(archive, 'w:gz') as output:
                output.add(source, arcname=source.name)
            commands_before = logs.read_text()
            result = subprocess.run(['bash', str(path), '--update'], env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No downgrade', result.stdout + result.stderr)
            self.assertEqual(configuration.read_bytes(), before)
            self.assertEqual(logs.read_text(), commands_before)
            version_file.write_text(original_version)
            with tarfile.open(archive, 'w:gz') as output:
                output.add(source, arcname=source.name)
            # First-install paths execute only in this temporary tree. Simulate root
            # inside the downloaded fixture; production privilege checks stay intact.
            cli_source=source/'src/usb_scanner_mqtt/cli.py'
            cli_source.write_text(cli_source.read_text().replace('if os.geteuid() != 0:', 'if False:'))
            with tarfile.open(archive,'w:gz') as output:
                output.add(source,arcname=source.name)
            # Force a fresh release copy so it includes that fixture-only root stub.
            shutil.rmtree((base/'opt/usb-scanner-mqtt/current').resolve())
            tty=base/'test-terminal'
            path.write_text(installer.replace('/dev/tty',str(tty)))
            stub('hostname','print("192.0.2.10 192.0.2.20")\n')
            configuration.unlink();tty.write_text('\n1\n1\n')
            result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            fresh=json.loads(configuration.read_text())
            self.assertTrue(fresh['setup_pending']);self.assertEqual(fresh['mqtt']['host'],'')
            self.assertTrue(fresh['web']['enabled'])
            self.assertIn('http://192.0.2.10:8765',result.stdout)
            self.assertIn('http://192.0.2.20:8765',result.stdout)
            # Re-running preserves an unfinished browser setup, without asking again.
            dirty=json.loads(configuration.read_text());dirty['scanner']['name']='Before reset';configuration.write_text(json.dumps(dirty))
            pending_bytes=configuration.read_bytes();tty.write_text('invalid language\n\ninvalid choice\n1\n')
            result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(configuration.read_bytes(),pending_bytes)
            self.assertIn('Already installed',result.stdout)
            # Exit and rejected reset do not touch configuration or restart service.
            for answer in ('', '0\n', '2\nno\n'):
                tty.write_text('\n'+answer);commands_before=logs.read_text()
                result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(configuration.read_bytes(),pending_bytes)
                self.assertEqual(logs.read_text(),commands_before)
            # Confirmed reset discards settings and queued scans, then starts browser setup.
            data=base/'var/lib/usb-scanner-mqtt';data.mkdir(parents=True,exist_ok=True)
            (data/'outbox.sqlite3').write_text('old queued data')
            # A failed download or service stop must preserve data even after confirmation.
            curl_stub=(fakebin/'curl').read_text();systemctl_stub=(fakebin/'systemctl').read_text()
            for command in ('curl','systemctl'):
                stub(command,'import sys\nsys.exit(1)\n')
                tty.write_text('\n2\nDELETE\n1\n')
                result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(configuration.read_bytes(),pending_bytes)
                self.assertEqual((data/'outbox.sqlite3').read_text(),'old queued data')
                (fakebin/command).write_text(curl_stub if command == 'curl' else systemctl_stub)
            tty.write_text('2\n2\nDELETE\n1\n')
            result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue(json.loads(configuration.read_text())['setup_pending'])
            self.assertNotEqual(configuration.read_bytes(),pending_bytes)
            self.assertFalse((data/'outbox.sqlite3').exists())
            self.assertIn('Bereits installiert:',result.stdout)
            self.assertIn('Browser-Einrichtung gewählt.',result.stdout)
            self.assertIn('Öffne einen dieser Links',result.stdout)
            self.assertNotIn('Already installed:',result.stdout)
            self.assertNotIn('Open one of these links',result.stdout)
            self.assertNotIn('language',json.loads(configuration.read_text()))
            self.assertIn('systemctl stop usb-scanner-mqtt.service',logs.read_text())
            # Current uninstall helper is localized even with an older installed wrapper.
            wrapper=base/'usr/local/bin/myscanner';original_wrapper=wrapper.read_text()
            wrapper.write_text('#!/bin/sh\nexit 99\n');wrapper.chmod(0o755)
            tty.write_text('2\n3\n0\n');commands_before=logs.read_text()
            result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Programm entfernen',result.stdout)
            self.assertIn('Abgebrochen.',result.stdout)
            self.assertNotIn('Remove program',result.stdout)
            self.assertEqual(logs.read_text(),commands_before)
            wrapper.write_text(original_wrapper)
            # Alternative initial setup in the terminal, web interface default yes.
            configuration.unlink()
            tty.write_text('\n'.join(['2','1','2','/dev/input/scanner','','Küche','','','','broker.example','','','-','','','',''])+'\n')
            result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            fresh=json.loads(configuration.read_text())
            self.assertFalse(fresh['setup_pending']);self.assertEqual(fresh['scanner']['name'],'Küche')
            self.assertTrue(fresh['web']['enabled']);self.assertEqual(fresh['mqtt']['host'],'broker.example')
            self.assertIn('AM Scanner eingestelltes Layout',result.stdout)
            self.assertIn('Anzeigename in Home Assistant',result.stdout)
            self.assertNotIn('Name shown in Home Assistant',result.stdout)
            # Headless installation also defaults to browser mode, not fake MQTT values.
            configuration.unlink();tty.unlink()
            result=subprocess.run(['bash',str(path),'--browser'],env={**env,'USB_SCANNER_INSTALL_LANGUAGE':'de'},text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue(json.loads(configuration.read_text())['setup_pending'])
            self.assertIn('Browser setup selected.',result.stdout)
            self.assertNotIn('Sprache wählen',result.stdout)
            # A genuinely new installation has no maintenance menu.
            configuration.unlink();shutil.rmtree(base/'opt/usb-scanner-mqtt')
            (base/'usr/local/bin/myscanner').unlink();tty.write_text('\n1\n')
            result=subprocess.run(['bash',str(path)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('Already installed',result.stdout)
            self.assertTrue(json.loads(configuration.read_text())['setup_pending'])


if __name__ == '__main__':
    unittest.main()
