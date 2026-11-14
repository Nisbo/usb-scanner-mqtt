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
            stub('curl',f'import sys,shutil\nif "-o" in sys.argv:\n shutil.copyfile({str(archive)!r},sys.argv[sys.argv.index("-o")+1])\nelse:\n print({json.dumps({"sha":commit})!r})\n')
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
            # Repair one missing distro dependency; do not reinstall every package.
            stub('dpkg-query','import sys\nprint("missing" if sys.argv[-1] == "python3-evdev" else "install ok installed")\n')
            run()
            self.assertIn('apt install -y --no-install-recommends python3-evdev',logs.read_text())
            self.assertEqual(configuration.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
