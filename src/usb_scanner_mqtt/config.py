"""Validated configuration; never print credentials in diagnostics."""
import ipaddress
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from .auth import valid_hash

DEFAULT_CONFIG = Path("/etc/usb-scanner-mqtt/config.json")


def defaults():
    return {
        "version": 1,
        "setup_pending": False,
        "web": {"enabled": False, "host": "0.0.0.0", "port": 8765, "auth_enabled": False, "password_hash": "", "auto_logout": False},
        "scan_send_enabled": True,
        "installation_id": uuid.uuid4().hex,
        "mqtt": {"host": "", "port": 1883, "user": "", "password": "",
                 "tls": False, "ca_file": "", "discovery_prefix": "homeassistant"},
        "scanner": {"id": "usb-scanner-1", "name": "USB Scanner", "device": "",
                    "layout": "us", "topic": "usb-scanner-mqtt/usb-scanner-1/scan"},
    }


def validate(config):
    if config.get("version") != 1:
        raise ValueError("Unsupported configuration version. Keep your existing installation.")
    config.setdefault("web", {"enabled": False, "host": "0.0.0.0", "port": 8765, "auth_enabled": False, "password_hash": "", "auto_logout": False})
    config.setdefault("setup_pending", False)
    if type(config['setup_pending']) is not bool:
        raise ValueError('setup_pending must be true or false.')
    config.setdefault("scan_send_enabled", True)
    web = config["web"]
    web.setdefault("auto_logout", False)
    web.setdefault("auth_enabled", False)
    web.setdefault("password_hash", "")
    if type(web['auto_logout']) is not bool or type(web['auth_enabled']) is not bool or not isinstance(web['password_hash'], str):
        raise ValueError('Invalid dashboard authentication settings.')
    if (web['password_hash'] and not valid_hash(web['password_hash'])) or (web['auth_enabled'] and not web['password_hash']):
        raise ValueError('Invalid dashboard password hash.')
    if type(config["scan_send_enabled"]) is not bool or type(web["enabled"]) is not bool:
        raise ValueError("Web enabled and scan sending must be true or false.")
    if not isinstance(web["host"], str) or not web["host"].strip():
        raise ValueError("Web bind address is required.")
    if type(web["port"]) is not int or not 1 <= web["port"] <= 65535:
        raise ValueError("Web port must be between 1 and 65535.")
    if config['setup_pending'] and not web['enabled']:
        raise ValueError('Browser setup requires the web interface.')
    mqtt, scanner = config["mqtt"], config["scanner"]
    if not re.fullmatch(r"[a-f0-9]{32}", config["installation_id"]):
        raise ValueError("Invalid installation_id.")
    if not isinstance(mqtt["host"], str) or (not config["setup_pending"] and not mqtt["host"].strip()):
        raise ValueError("MQTT host is required.")
    host = mqtt['host']
    if host and ('/' in host or any(char.isspace() for char in host)):
        raise ValueError('Enter only the MQTT hostname or IP, without http://, mqtt:// or a port.')
    if ':' in host:
        try:
            ipaddress.IPv6Address(host)
        except ipaddress.AddressValueError:
            raise ValueError('Enter the MQTT port separately from the hostname or IP.') from None
    if type(mqtt["port"]) is not int or not 1 <= mqtt["port"] <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    if type(mqtt["tls"]) is not bool:
        raise ValueError("tls must be true or false.")
    for key in ("user", "password", "ca_file"):
        if not isinstance(mqtt[key], str):
            raise ValueError(f"MQTT {key} must be text.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", scanner["id"]):
        raise ValueError("Scanner ID: use letters, numbers, '-' or '_' (max. 64).")
    if not isinstance(scanner["name"], str) or not scanner["name"].strip():
        raise ValueError("Scanner name is required.")
    if scanner["layout"] not in ("us", "de", "gb", "fr", "es"):
        raise ValueError("Supported keyboard layouts: us, de, gb, fr, es.")
    scanner.setdefault("output_profile", "standard")
    if scanner["output_profile"] not in ("standard", "alt-pair-latin1"):
        raise ValueError("Supported output profiles: standard, alt-pair-latin1.")
    device = scanner["device"]
    if not isinstance(device, str) or (not device and not config["setup_pending"]) or (device and (not device.startswith("/dev/input/") or ".." in Path(device).parts)):
        raise ValueError("Choose a scanner device under /dev/input/.")
    for topic in (scanner["topic"], mqtt["discovery_prefix"]):
        if not isinstance(topic, str) or not topic or any(c in topic for c in ("+", "#", "\0")):
            raise ValueError("MQTT topics must not be empty or contain +, # or NUL.")
        if len(topic.encode()) > 512:
            raise ValueError("MQTT topic is too long.")
    return config


def load(path=DEFAULT_CONFIG):
    with Path(path).open(encoding="utf-8") as stream:
        return validate(json.load(stream))


def save(config, path=DEFAULT_CONFIG):
    validate(config)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(config, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
