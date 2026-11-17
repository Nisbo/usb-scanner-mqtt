"""Local addresses and removal of this application's files only."""
import ipaddress
import shutil
import socket
import subprocess
from pathlib import Path

from .terminal_i18n import text as t

SERVICE = 'usb-scanner-mqtt.service'


def ipv4_addresses():
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=3, check=False)
        candidates = result.stdout.split() if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        candidates = []
    if not candidates:
        try:
            candidates = [item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
        except OSError:
            candidates = []
    addresses = set()
    for candidate in candidates:
        try:
            address = ipaddress.IPv4Address(candidate)
            if not (address.is_loopback or address.is_unspecified or address.is_multicast):
                addresses.add(address)
        except ipaddress.AddressValueError:
            continue
    return [str(address) for address in sorted(addresses)]


def web_urls(config):
    web = config['web']
    if not web['enabled']:
        return []
    host = web['host']
    if host == '0.0.0.0':
        hosts = ipv4_addresses() or ['127.0.0.1']
    else:
        try:
            hosts = [str(ipaddress.IPv4Address(host))]
        except ipaddress.AddressValueError:
            try:
                hosts = list(dict.fromkeys(item[4][0] for item in
                    socket.getaddrinfo(host, None, socket.AF_INET)))
            except OSError:
                hosts = []
    return [f'http://{address}:{web["port"]}' for address in hosts]


def print_web_addresses(config):
    urls = web_urls(config)
    if not urls:
        if config['web']['enabled']:
            print(t('Cannot resolve the web bind address to IPv4. Check the configured web host.'))
            return
        print(t('Web interface is off. Enable it with: myscanner set gui true'))
        return
    print(t('\nOpen one of these links in your browser to continue setup:'))
    for url in urls:
        print('  ' + url)
    if all('127.0.0.1:' in url or 'localhost:' in url for url in urls):
        print(t('Open this link in a browser on this Linux computer.'))


def remove_installation(purge=False, root=Path('/')):
    """Caller confirms removal and requires root. root is injectable for isolated tests."""
    import fcntl
    root = Path(root)
    lock_path = root / 'run/lock/usb-scanner-mqtt.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(t('Another installation, update or removal is running.')) from None
        unit = root / 'etc/systemd/system' / SERVICE
        active = subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE], check=False)
        if active.returncode not in (0, 3, 4):
            raise ValueError(t('Cannot determine service status; nothing was removed.'))
        if active.returncode == 0:
            subprocess.run(['systemctl', 'stop', SERVICE], check=True)
        if unit.exists() or unit.is_symlink():
            subprocess.run(['systemctl', 'disable', SERVICE], check=True)
        paths = [unit, root / 'usr/local/bin/myscanner', root / 'opt/usb-scanner-mqtt']
        if purge:
            paths += [root / 'etc/usb-scanner-mqtt', root / 'var/lib/usb-scanner-mqtt']
        for path in paths:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'reset-failed', SERVICE], check=False, capture_output=True)
    # Keep the lock inode so a concurrent installer cannot acquire a different lock.
    print(t('Program removed. ') + (t('Settings and queued scans deleted.') if purge else t('Settings and queued scans kept for reinstallation.')))
    print(t('Shared system packages and Proxmox settings were not removed. Remove the old MQTT device in Home Assistant manually if desired.'))


def uninstall(mode=None):
    if mode is None:
        print(t('1. Remove program; keep settings and queued scans (recommended)'))
        print(t('2. Remove program AND all settings and queued scans'))
        print(t('0. Cancel'))
        choice = input(t('Choice [1]: ')).strip() or '1'
        if choice == '0':
            print(t('Cancelled.')); return
        if choice not in ('1', '2'):
            raise ValueError(t('Choose 1, 2 or 0.'))
        mode = 'purge' if choice == '2' else 'keep'
    confirmation = 'DELETE' if mode == 'purge' else t('yes')
    print(t('This stops the scanner service.') + (t(' All settings, passwords and queued scans will be deleted.') if mode == 'purge' else t(' Settings and queued scans will be kept.')))
    if input(t('Type {confirmation} to confirm: ').format(confirmation=confirmation)).strip() != confirmation:
        print(t('Cancelled.')); return
    remove_installation(purge=mode == 'purge')
