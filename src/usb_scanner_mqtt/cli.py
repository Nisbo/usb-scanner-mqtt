"""One small entry point for setup, operation and updates."""
import argparse
import asyncio
import getpass
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from .terminal_i18n import text as t

from . import __version__
from . import config as settings

SERVICE = "usb-scanner-mqtt.service"


def root_required():
    if os.geteuid() != 0:
        raise ValueError("Please run this command as root (sudo myscanner ...).")


def restart_if_running():
    active = subprocess.run(["systemctl", "is-active", "--quiet", SERVICE], check=False)
    if active.returncode == 0:
        subprocess.run(["systemctl", "restart", SERVICE], check=True)


def available_devices():
    stable = sorted(Path("/dev/input/by-id").glob("*event-kbd"))
    fallback = Path("/dev/input/barcode-scanner")
    if fallback.exists():
        stable.append(fallback)
    if not stable:
        stable = sorted(Path("/dev/input").glob("event*"))
    return [str(path) for path in stable]


def ask(label, default=""):
    result = input(f"{t(label)}" + (f" [{default}]" if default else "") + ": ").strip()
    return result or default


def device_name(path):
    try:
        from evdev import InputDevice
        device = InputDevice(path)
        try:
            return device.name
        finally:
            device.close()
    except (ImportError, OSError):
        return Path(path).name


def setup(path, mode=None):
    root_required()
    is_new = not path.exists()
    config = settings.load(path) if not is_new else settings.defaults()
    if mode is None:
        print('How would you like to set up the scanner? / Einrichtung wählen:')
        print('  1. Browser (recommended / empfohlen)')
        print('  2. Terminal')
        choice = ask('Choice / Auswahl', '1')
        if choice not in ('1', '2'):
            raise ValueError('Choose 1 for browser or 2 for terminal.')
        mode = 'browser' if choice == '1' else 'shell'
    if mode == 'browser':
        config['web']['enabled'] = True
        if is_new:
            config['setup_pending'] = True
        settings.save(config, path)
        restart_if_running()
        from .maintenance import print_web_addresses
        print(t('Browser setup selected. Wait for installation to finish, then open a link below.'))
        print_web_addresses(config)
        return
    scanner, mqtt = config["scanner"], config["mqtt"]
    print(t("USB Scanner MQTT — setup (press Enter to keep an existing value)"))
    devices = available_devices()
    if devices:
        print(t('Detected input devices (choose your scanner, not a regular keyboard):'))
    else:
        print(t('No input devices found. Check USB/passthrough or enter the device path manually.'))
    for index, device in enumerate(devices, 1):
        print(f"  {index}. {device_name(device)} — {device}")
    value = ask(t("Scanner device: path or number"), scanner["device"] or (devices[0] if len(devices) == 1 else ""))
    if value.isdecimal() and 1 <= int(value) <= len(devices):
        value = devices[int(value) - 1]
    scanner["device"] = value
    old_id = scanner["id"]
    scanner["id"] = ask(t("Scanner ID (unique across your scanners)"), old_id)
    scanner["name"] = ask(t("Name shown in Home Assistant"), scanner["name"])
    print(t('Keyboard layout: fixed starting value, not auto-detected. If unsure, keep it and use browser calibration later.'))
    scanner["layout"] = ask(t("Layout configured ON the scanner (us/de/gb/fr/es)"), scanner["layout"])
    print(t('Output profile: how extra characters are read. Keep standard if unsure; calibration checks it.'))
    scanner["output_profile"] = ask(t("Output profile (standard/alt-pair-latin1)"), scanner.get("output_profile", "standard"))
    if scanner["topic"] == f"usb-scanner-mqtt/{old_id}/scan":
        scanner["topic"] = f"usb-scanner-mqtt/{scanner['id']}/scan"
    print(t('Scan topic: MQTT address used for scan messages. The suggested topic is generated from the scanner ID.'))
    scanner["topic"] = ask(t("MQTT scan topic"), scanner["topic"])
    print(t('Broker address: hostname or IP only, without http://, https://, mqtt:// or a port.'))
    mqtt["host"] = ask(t("MQTT broker IP or hostname"), mqtt["host"])
    print(t('Use TLS only if your broker provides a TLS connection; usually port 8883 instead of 1883.'))
    mqtt["tls"] = ask(t("Use TLS? (yes/no)"), t("yes") if mqtt["tls"] else t("no")).lower() in ("yes", "y", "ja", "j")
    mqtt["port"] = int(ask(t("MQTT port"), str(8883 if mqtt["tls"] and mqtt["port"] == 1883 else mqtt["port"])))
    mqtt["user"] = ask(t("MQTT username (use '-' for no authentication)"), mqtt["user"])
    if mqtt["user"] == "-":
        mqtt["user"] = ""
        mqtt["password"] = ""
    elif mqtt["user"]:
        password = getpass.getpass(t("MQTT password (Enter keeps existing password): "))
        if password or not mqtt["password"]:
            mqtt["password"] = password
    if mqtt["tls"]:
        value = ask(t("Custom CA certificate path (or '-' for system certificates)"), mqtt["ca_file"])
        mqtt["ca_file"] = "" if value == "-" else value
    web = config["web"]
    web["enabled"] = ask(t("Enable internal web interface? (yes/no)"), t("yes") if web["enabled"] or is_new else t("no")).lower() in ("yes", "y", "ja", "j")
    if web["enabled"]:
        web["host"] = ask(t("Web bind address"), web["host"])
        web["port"] = int(ask(t("Web port"), str(web["port"])))
    config["scan_send_enabled"] = ask(t("Send scans over MQTT? (yes/no; no discards new test scans)"), t("yes") if config["scan_send_enabled"] else t("no")).lower() in ("yes", "y", "ja", "j")
    config["setup_pending"] = False
    settings.save(config, path)
    print(t("Configuration saved: {path} (permissions 0600).").format(path=path))
    print(t("The receiver uses the selected scanner exclusively while running."))
    print(t("USB passthrough must already be configured if this runs inside an LXC/VM."))
    restart_if_running()


def set_value(path, key, value):
    root_required()
    config = settings.load(path)
    destinations = {
        "gui": ("web", "enabled"), "web-host": ("web", "host"),
        "web-port": ("web", "port"), "send": (None, "scan_send_enabled"),
        "host": ("mqtt", "host"), "ip": ("mqtt", "host"),
        "port": ("mqtt", "port"), "user": ("mqtt", "user"),
        "password": ("mqtt", "password"), "pw": ("mqtt", "password"),
        "tls": ("mqtt", "tls"), "ca-file": ("mqtt", "ca_file"),
        "discovery-prefix": ("mqtt", "discovery_prefix"),
        "output-profile": ("scanner", "output_profile"),
        "device": ("scanner", "device"), "layout": ("scanner", "layout"),
        "name": ("scanner", "name"), "topic": ("scanner", "topic"),
    }
    if key not in destinations:
        raise ValueError("Unknown setting. Available: " + ", ".join(destinations))
    section, name = destinations[key]
    if name == "password":
        if value is not None:
            raise ValueError("Use 'myscanner set password' without a value; it prompts securely.")
        value = getpass.getpass("New MQTT password: ")
    elif value is None:
        raise ValueError("A value is required.")
    elif name == "port":
        value = int(value)
    elif name in ("tls", "enabled", "scan_send_enabled"):
        if value.lower() not in ("true", "false", "yes", "no", "on", "off"):
            raise ValueError("Use true or false.")
        value = value.lower() in ("true", "yes", "on")
    (config if section is None else config[section])[name] = value
    settings.save(config, path)
    restart_if_running()
    print("Setting saved. Running service restarted.")


def update():
    root_required()
    url = "https://raw.githubusercontent.com/Nisbo/usb-scanner-mqtt/main/install.sh"
    with tempfile.TemporaryDirectory(prefix="myscanner-update-") as directory:
        path = Path(directory) / "install.sh"
        with urllib.request.urlopen(url, timeout=30) as response:
            path.write_bytes(response.read(1024 * 1024))
        subprocess.run(["bash", str(path), "--update"], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="USB HID scanner to MQTT and Home Assistant discovery")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, default=settings.DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    setup_parser = commands.add_parser("setup", help="Choose browser (default) or terminal setup; keeps existing values")
    setup_parser.add_argument('--mode', choices=('browser', 'shell'))
    commands.add_parser('web', help='Show browser URLs using detected IPv4 addresses')
    removal = commands.add_parser('uninstall', help='Remove the program; optionally remove settings and queued scans')
    removal_mode = removal.add_mutually_exclusive_group()
    removal_mode.add_argument('--keep-data', action='store_const', const='keep', dest='mode')
    removal_mode.add_argument('--purge', action='store_const', const='purge', dest='mode')
    setting = commands.add_parser("set", help="Change one setting and restart the running receiver")
    setting.add_argument("key")
    setting.add_argument("value", nargs="?")
    commands.add_parser("status", help="Service status and redacted configuration")
    commands.add_parser("logs", help="Follow service logs; barcode contents are not logged")
    commands.add_parser("reset-login", help="Disable dashboard login and remove its password; preserves other settings")
    commands.add_parser("restart")
    commands.add_parser("update")
    commands.add_parser("test", help="Read scans locally without sending MQTT; stops receiver temporarily")
    commands.add_parser("check-config", help="Validate configuration without printing secrets")
    run = commands.add_parser("run", help="Run receiver (normally started by systemd)")
    run.add_argument("--state-dir", type=Path, default=Path("/var/lib/usb-scanner-mqtt"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if args.command == "setup":
            setup(args.config, args.mode)
        elif args.command == 'web':
            from .maintenance import print_web_addresses
            print_web_addresses(settings.load(args.config))
        elif args.command == 'uninstall':
            root_required()
            from .maintenance import uninstall
            uninstall(args.mode)
        elif args.command == "set":
            set_value(args.config, args.key, args.value)
        elif args.command == "reset-login":
            root_required()
            config = settings.load(args.config)
            config['web'].update(auth_enabled=False, password_hash='')
            settings.save(config, args.config)
            restart_if_running()
            print('Dashboard password protection disabled and password removed. Other settings preserved.')
        elif args.command == "update":
            update()
        elif args.command in ("restart", "logs"):
            if args.command == "restart":
                root_required()
            subprocess.run(["systemctl", "restart", SERVICE] if args.command == "restart" else
                           ["journalctl", "-u", SERVICE, "-n", "30", "-f"], check=True)
        elif args.command == "status":
            config = settings.load(args.config)
            print(f"Version: {__version__}")
            print(f"Scanner: {config['scanner']['name']} ({config['scanner']['id']})")
            print(f"Device: {config['scanner']['device']} | layout: {config['scanner']['layout']}")
            print(f"MQTT: {config['mqtt']['host']}:{config['mqtt']['port']} | TLS: {config['mqtt']['tls']}")
            print(f"Web enabled: {config['web']['enabled']} | bind: {config['web']['host']}:{config['web']['port']}")
            if config.get("setup_pending", False):
                print("Initial setup pending. Open the browser using: myscanner web")
            print(f"MQTT scan sending: {config['scan_send_enabled']}")
            print(f"Output profile: {config['scanner']['output_profile']}")
            print(f"Scan topic: {config['scanner']['topic']}")
            subprocess.run(["systemctl", "status", "--no-pager", SERVICE], check=False)
        elif args.command == "check-config":
            settings.load(args.config)
            print(t("Configuration valid."))
        elif args.command == "run":
            from .receiver import run
            asyncio.run(run(settings.load(args.config), args.state_dir, args.config))
        elif args.command == "test":
            root_required()
            config = settings.load(args.config)
            if config.get("setup_pending", False):
                raise ValueError("Complete setup first: myscanner web or myscanner setup --mode shell")
            from .receiver import read_device
            active = subprocess.run(["systemctl", "is-active", "--quiet", SERVICE], check=False).returncode == 0
            if active:
                subprocess.run(["systemctl", "stop", SERVICE], check=True)
            print("Local test only: no MQTT is sent. Scan a code; Ctrl+C finishes.", flush=True)
            try:
                asyncio.run(read_device(config, lambda text: print(json.dumps(text, ensure_ascii=False), flush=True),
                                        lambda online: None, asyncio.Event()))
            finally:
                if active:
                    subprocess.run(["systemctl", "start", SERVICE], check=True)
    except KeyboardInterrupt:
        return 0
    except (ValueError, KeyError, OSError, EOFError, subprocess.CalledProcessError) as error:
        # Never include config values/passwords in generic validation errors.
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
