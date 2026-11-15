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
    result = input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip()
    return result or default


def setup(path):
    root_required()
    config = settings.load(path) if path.exists() else settings.defaults()
    scanner, mqtt = config["scanner"], config["mqtt"]
    print("USB Scanner MQTT — setup (press Enter to keep an existing value)")
    devices = available_devices()
    for index, device in enumerate(devices, 1):
        print(f"  {index}. {device}")
    value = ask("Scanner device: path or number", scanner["device"] or (devices[0] if len(devices) == 1 else ""))
    if value.isdecimal() and 1 <= int(value) <= len(devices):
        value = devices[int(value) - 1]
    scanner["device"] = value
    old_id = scanner["id"]
    scanner["id"] = ask("Scanner ID (unique across your scanners)", old_id)
    scanner["name"] = ask("Name shown in Home Assistant", scanner["name"])
    scanner["layout"] = ask("Layout configured ON the scanner (us/de)", scanner["layout"])
    if scanner["topic"] == f"usb-scanner-mqtt/{old_id}/scan":
        scanner["topic"] = f"usb-scanner-mqtt/{scanner['id']}/scan"
    scanner["topic"] = ask("MQTT scan topic", scanner["topic"])
    mqtt["host"] = ask("MQTT broker IP or hostname", mqtt["host"])
    mqtt["tls"] = ask("Use TLS? (yes/no)", "yes" if mqtt["tls"] else "no").lower() in ("yes", "y", "ja", "j")
    mqtt["port"] = int(ask("MQTT port", str(8883 if mqtt["tls"] and mqtt["port"] == 1883 else mqtt["port"])))
    mqtt["user"] = ask("MQTT username (use '-' for no authentication)", mqtt["user"])
    if mqtt["user"] == "-":
        mqtt["user"] = ""
        mqtt["password"] = ""
    elif mqtt["user"]:
        password = getpass.getpass("MQTT password (Enter keeps existing password): ")
        if password or not mqtt["password"]:
            mqtt["password"] = password
    if mqtt["tls"]:
        value = ask("Custom CA certificate path (or '-' for system certificates)", mqtt["ca_file"])
        mqtt["ca_file"] = "" if value == "-" else value
    web = config["web"]
    web["enabled"] = ask("Enable internal web interface without login? (yes/no)", "yes" if web["enabled"] else "no").lower() in ("yes", "y", "ja", "j")
    if web["enabled"]:
        web["host"] = ask("Web bind address", web["host"])
        web["port"] = int(ask("Web port", str(web["port"])))
    config["scan_send_enabled"] = ask("Send scans over MQTT? (yes/no; no discards new test scans)", "yes" if config["scan_send_enabled"] else "no").lower() in ("yes", "y", "ja", "j")
    settings.save(config, path)
    print(f"Configuration saved: {path} (permissions 0600).")
    print("The receiver uses the selected scanner exclusively while running.")
    print("USB passthrough must already be configured if this runs inside an LXC/VM.")
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
    commands.add_parser("setup", help="Interactive setup; preserves existing values")
    setting = commands.add_parser("set", help="Change one setting and restart the running receiver")
    setting.add_argument("key")
    setting.add_argument("value", nargs="?")
    commands.add_parser("status", help="Service status and redacted configuration")
    commands.add_parser("logs", help="Follow service logs; barcode contents are not logged")
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
            setup(args.config)
        elif args.command == "set":
            set_value(args.config, args.key, args.value)
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
            print(f"MQTT scan sending: {config['scan_send_enabled']}")
            print(f"Scan topic: {config['scanner']['topic']}")
            subprocess.run(["systemctl", "status", "--no-pager", SERVICE], check=False)
        elif args.command == "check-config":
            settings.load(args.config)
            print("Configuration valid.")
        elif args.command == "run":
            from .receiver import run
            asyncio.run(run(settings.load(args.config), args.state_dir, args.config))
        elif args.command == "test":
            root_required()
            config = settings.load(args.config)
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
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        # Never include config values/passwords in generic validation errors.
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
