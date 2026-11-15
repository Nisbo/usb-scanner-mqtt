"""Validated configuration; never print credentials in diagnostics."""
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

DEFAULT_CONFIG = Path("/etc/usb-scanner-mqtt/config.json")


def defaults():
    return {
        "version": 1,
        "web": {"enabled": False, "host": "0.0.0.0", "port": 8765},
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
    config.setdefault("web", {"enabled": False, "host": "0.0.0.0", "port": 8765})
    config.setdefault("scan_send_enabled", True)
    web = config["web"]
    if type(config["scan_send_enabled"]) is not bool or type(web["enabled"]) is not bool:
        raise ValueError("Web enabled and scan sending must be true or false.")
    if not isinstance(web["host"], str) or not web["host"].strip():
        raise ValueError("Web bind address is required.")
    if type(web["port"]) is not int or not 1 <= web["port"] <= 65535:
        raise ValueError("Web port must be between 1 and 65535.")
    mqtt, scanner = config["mqtt"], config["scanner"]
    if not re.fullmatch(r"[a-f0-9]{32}", config["installation_id"]):
        raise ValueError("Invalid installation_id.")
    if not isinstance(mqtt["host"], str) or not mqtt["host"].strip():
        raise ValueError("MQTT host is required.")
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
    if scanner["layout"] not in ("us", "de"):
        raise ValueError("Supported keyboard layouts: us, de.")
    device = scanner["device"]
    if not isinstance(device, str) or not device.startswith("/dev/input/") or ".." in Path(device).parts:
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
