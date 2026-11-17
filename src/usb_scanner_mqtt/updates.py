"""Pinned GitHub updates. Release channels never execute files from main."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import urllib.request

from . import __version__
from . import config as settings
from .update_http import UpdateError, github

REPOSITORY = 'Nisbo/usb-scanner-mqtt'
CHANNELS = ('stable', 'prerelease', 'dev')
INSTALL_ROOT = Path('/opt/usb-scanner-mqtt/current')
STATE_DIR = Path('/var/lib/usb-scanner-mqtt')



def version_key(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-(dev|alpha|beta|rc)(?:\.(\d+))?)?', value)
    if not match:
        raise ValueError('Unsupported update version.')
    major, minor, patch, stage, number = match.groups()
    return (int(major), int(minor), int(patch), {'dev': 0, 'alpha': 1, 'beta': 2, 'rc': 3, None: 4}[stage], int(number or 0))


def revision(root=INSTALL_ROOT):
    try:
        value = (root / 'REVISION').read_text().strip()
        return value if re.fullmatch('[a-f0-9]{40}', value) else None
    except OSError:
        return None


def resolve(channel):
    if channel not in CHANNELS:
        raise ValueError('Choose stable, prerelease or dev.')
    if channel == 'dev':
        sha = github('/commits/dev')['sha']
        tag = None
    else:
        if channel == 'stable':
            release = github('/releases/latest')
        else:
            releases = github('/releases?per_page=100')
            candidates = []
            for release in releases:
                if release.get('draft'):
                    continue
                try:
                    candidates.append((version_key(release['tag_name']), release))
                except (ValueError, KeyError, TypeError):
                    continue
            if not candidates:
                raise ValueError('No published release available.')
            release = max(candidates, key=lambda item: item[0])[1]
        tag = release['tag_name']
        version_key(tag)  # Strict tag grammar also protects URLs and installer arguments.
        if release.get('draft') or (channel == 'stable' and release.get('prerelease')):
            raise ValueError('No matching published release available.')
        sha = github('/commits/' + tag)['sha']
    if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha):
        raise ValueError('Invalid GitHub revision.')
    # Read the version from exactly the revision which will be installed.
    url = f'https://raw.githubusercontent.com/{REPOSITORY}/{sha}/src/usb_scanner_mqtt/__init__.py'
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            source = response.read(4096).decode('utf-8')
    except (OSError, UnicodeError):
        raise ValueError('Could not read the update version. Try again later.') from None
    match = re.search(r'^__version__ = "([^"]+)"$', source, re.M)
    if not match:
        raise ValueError('Invalid update version.')
    version = match[1]
    version_key(version)
    if tag and version_key(tag) != version_key(version):
        raise ValueError('Release tag and program version differ.')
    return {'channel': channel, 'revision': sha, 'version': version,
            'release_url': f'https://github.com/{REPOSITORY}/releases/tag/{tag}' if tag else None,
            'url': f'https://github.com/{REPOSITORY}/' + ('releases/tag/' + tag if tag else 'commits/dev/')}


def assess(target, installed_version=__version__, installed_revision=None):
    result = {**target, 'installed_version': installed_version, 'installed_revision': installed_revision,
              'available': False, 'status': 'current'}
    if version_key(target['version']) < version_key(installed_version):
        result['status'] = 'waiting'
        return result
    if installed_revision == target['revision']:
        return result
    if installed_revision:
        comparison = github(f'/compare/{installed_revision}...{target["revision"]}')
        if comparison.get('status') not in ('ahead', 'identical'):
            result['status'] = 'waiting'
            return result
    elif target['channel'] == 'dev' or version_key(target['version']) == version_key(installed_version):
        # Unknown source provenance: never silently replace an equal-version build.
        result['status'] = 'waiting'
        return result
    if installed_revision:
        result['changes_url'] = f'https://github.com/{REPOSITORY}/compare/{installed_revision}...{target["revision"]}'
    result.update(available=True, status='available')
    return result


def check(channel, installed_version=__version__, installed_revision=None):
    try:
        return assess(resolve(channel), installed_version, installed_revision if installed_revision is not None else revision())
    except (KeyError, TypeError, AttributeError):
        raise ValueError('Invalid GitHub update metadata. Try again later.') from None


def describe(result):
    print('Installed: ' + result['installed_version'])
    print('Channel: ' + result['channel'])
    print('Available build: ' + result['version'] + ' · ' + result['revision'][:8])
    print({'available': 'Update available.', 'waiting': 'This channel has not caught up with your installed build. No downgrade.',
           'current': 'You are up to date.'}[result['status']])
    print('Changes: ' + result['url'])


def write_status(value, state_dir=STATE_DIR):
    value = {**value, 'pid': os.getpid()}
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.update-', dir=state_dir)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
        os.replace(name, state_dir / 'update-status.json')
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_status(state_dir=STATE_DIR):
    try:
        value = json.loads((state_dir / 'update-status.json').read_text())
        if not isinstance(value, dict):
            return {'phase': 'idle'}
        if value.get('phase') in ('starting', 'checking', 'installing') and type(value.get('pid')) is int and value['pid'] > 0:
            try:
                os.kill(value['pid'], 0)
            except ProcessLookupError:
                return {'phase': 'error', 'error': 'Update interrupted. Check for updates and try again.'}
        return value
    except (OSError, ValueError):
        return {'phase': 'idle'}


def install(config_path, expected=None, background=False):
    if Path(config_path) != settings.DEFAULT_CONFIG:
        raise ValueError('Updates require the standard system installation and configuration path.')
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE_DIR / 'update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('An update is already running.') from None
        try:
            write_status({'phase': 'checking'})
            channel = settings.load(config_path)['update_channel']
            target = check(channel)
            if expected and target['revision'] != expected:
                raise ValueError('Update target changed. Check for updates again.')
            if not target['available']:
                write_status({'phase': 'complete', 'result': target})
                return target
            write_status({'phase': 'installing', 'result': target})
            with tempfile.TemporaryDirectory(prefix='myscanner-update-') as directory:
                path = Path(directory) / 'install.sh'
                url = f'https://raw.githubusercontent.com/{REPOSITORY}/{target["revision"]}/install.sh'
                with urllib.request.urlopen(url, timeout=30) as response:
                    script = response.read(1024 * 1024 + 1)
                if len(script) > 1024 * 1024:
                    raise ValueError('Installer too large.')
                path.write_bytes(script)
                command = ['bash', str(path), '--update', '--revision=' + target['revision']]
                if background:
                    command.append('--non-interactive')
                subprocess.run(command, check=True)
            write_status({'phase': 'complete', 'result': target})
            return target
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            details = {'error_code': error.code, 'retry_at': error.retry_at} if isinstance(error, UpdateError) else {}
            write_status({'phase': 'error', 'error': str(error) if isinstance(error, UpdateError) else 'Update failed. Check the service log: journalctl -u usb-scanner-mqtt-update', **details})
            raise


class UpdateManager:
    """Network checks in a thread; installation in an independent systemd unit."""
    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.lock = threading.Lock()
        self.result = None
        self.checking = False
        self.error = None
        self.error_code = None
        self.retry_at = None

    def snapshot(self):
        with self.lock:
            return {'channel': self.dashboard.config['update_channel'], 'installed_version': __version__,
                    'installed_revision': revision(), 'checking': self.checking, 'result': self.result,
                    'error': self.error, 'error_code': self.error_code, 'retry_at': self.retry_at, 'job': read_status()}

    def set_channel(self, channel):
        if channel not in CHANNELS:
            raise ValueError('Choose stable, prerelease or dev.')
        with self.lock, self.dashboard.settings_lock:
            if self.checking or read_status().get('phase') in ('checking', 'installing', 'starting'):
                raise ValueError('An update or check is already running.')
            conf = settings.load(self.dashboard.path)
            conf['update_channel'] = channel
            settings.save(conf, self.dashboard.path)
            self.dashboard.config['update_channel'] = channel
            self.result = None
            self.error = None
            self.error_code = None
            self.retry_at = None

    def start_check(self):
        with self.lock:
            if self.checking:
                return
            phase = read_status().get('phase')
            if phase in ('starting', 'checking', 'installing'):
                raise ValueError('An update is already running.')
            if phase in ('complete', 'error'):
                write_status({'phase': 'idle'})
            self.checking = True
            self.result = None
            self.error = None
            self.error_code = None
            self.retry_at = None
            channel = self.dashboard.config['update_channel']
        def worker():
            try:
                value = check(channel)
                with self.lock:
                    self.result = value
            except (OSError, ValueError, KeyError, TypeError) as error:
                with self.lock:
                    self.error = str(error) if isinstance(error, UpdateError) else 'Update check failed. Check Internet access or try again later (GitHub request limit).'
                    self.error_code = error.code if isinstance(error, UpdateError) else None
                    self.retry_at = error.retry_at if isinstance(error, UpdateError) else None
            finally:
                with self.lock:
                    self.checking = False
        threading.Thread(target=worker, daemon=True).start()

    def start_install(self):
        with self.lock:
            if self.checking or not self.result or not self.result['available']:
                raise ValueError('Check for updates first.')
            if read_status().get('phase') in ('starting', 'checking', 'installing'):
                raise ValueError('An update is already running.')
            expected = self.result['revision']
            write_status({'phase': 'starting'})
            try:
                subprocess.run(['systemd-run', '--unit=usb-scanner-mqtt-update', '--collect',
                                '--description=USB Scanner MQTT update', '/usr/local/bin/myscanner',
                                '--config', str(self.dashboard.path), 'update', '--non-interactive', '--expected=' + expected],
                               check=True, capture_output=True, timeout=15)
            except (OSError, subprocess.SubprocessError):
                write_status({'phase': 'error', 'error': 'Could not start update. Use myscanner update in the Linux terminal.'})
                raise ValueError('Could not start update. Use myscanner update in the Linux terminal.') from None
