# Technical background

[Back to the simple guide](../README.md) · [Deutsch](TECHNICAL_de.md)

These details supplement the user guide. You do not need to work through them to
install or use the program.

## Installation and files

The installer supports Debian 12+/Ubuntu 24.04+ with systemd and Python 3.11+.
It installs missing packages through apt: `ca-certificates`, `curl`, `python3`,
`python3-venv`, `python3-evdev` and `python3-paho-mqtt`. The private Python environment
uses distribution packages through `--system-site-packages`; no compiler, pip
downloads, MQTT broker or separate web server are installed.

Downloads are pinned to a Git commit to avoid mixing revisions. Current and previous
application revisions are kept. Repeated installation and updates preserve settings
and the persistent outbox. An immediate service-restart failure restores the previous
application where possible; this is not a full rollback of package installation.

| Path | Contents |
| --- | --- |
| `/etc/usb-scanner-mqtt/config.json` | Settings and credentials, mode 0600 |
| `/var/lib/usb-scanner-mqtt/outbox.sqlite3` | Queued MQTT scans, mode 0600 |
| `/opt/usb-scanner-mqtt/` | Application revisions and Python environment |
| `/usr/local/bin/myscanner` | Shell command |

The service runs as root for input-device access, with systemd restrictions.
Configuration and state directories are writable. Normal logs omit passwords and
scan text. Explicit tests, MQTT messages and the outbox contain actual contents.
Scanned text is never executed; scanned URLs are never opened automatically.

## Device access and limits

One scanner per installation is supported. Multiple concurrent scanners and automatic
removal of obsolete Home Assistant discovery entries are not implemented yet.

Prefer a stable `/dev/input/by-id/…-event-kbd` path over changing `eventN` numbers.
VM/container device access must be configured separately. The installer does not
change host/container configuration. Container boot without a scanner and USB hotplug
depend on this passthrough configuration. The receiver retries opening missing devices.

## MQTT and Home Assistant

The connection uses MQTT 5. Default topic:

```text
usb-scanner-mqtt/usb-scanner-1/scan
```

Example scan message:

```json
{"ean":"0012345678905","scanner":"usb-scanner-1","scan_id":"unique-scan-id","timestamp":"2026-01-01T12:00:00+00:00"}
```

- `ean` stays a string, including QR text and leading zeroes.
- Every new completed scan has a fresh ID, even for identical contents.
- Retries of the same queued message preserve its ID and original topic.
- Scans use QoS 1 and **no retain**. Consumers should deduplicate by scanner and scan
  ID; there is no unconditional exactly-once guarantee.
- A broker acknowledgement does not confirm processing in Home Assistant.

Up to 1000 pending scans are stored persistently. A full outbox reports an error
without displacing existing entries. This protects against MQTT outages. If Home
Assistant is offline while the broker is connected, it can still miss non-retained messages.

Discovery and availability are retained. HA birth at `<discovery_prefix>/status`
(default `homeassistant/status`) re-announces discovery without replaying old scans.
Broker permissions must allow these publications and the subscription. Availability
requires both an open input device and an MQTT connection.

The **Last scan** sensor has `barcode`, `scanner`, `scan_id` and `timestamp` attributes.
For text longer than 255 characters, the state is `QR scan`; full text stays in the
`barcode` attribute. Maximum scan length is 4096 characters.

For HA List Manager, use its JSON MQTT scanner with barcode field `ean`, scanner
field `scanner` and scan-ID field `scan_id`. Process the same messages through only
one scanner source.

## Reception and calibration

Supported keyboard layouts are US, German, British English, French (AZERTY) and
Spanish. Shift, Caps and common AltGr characters are evaluated; French and Spanish
accent sequences are supported. Enter, keypad Enter and Tab finish scans. Unknown
sequences reject the scan. Partial input expires after two seconds; partial text is
never sent as a replacement.

Calibration compares all five layouts and both output profiles with known expected
text. Direct keystrokes prefer the standard profile. Only a current, unambiguous,
character-for-character match can be applied. Comparison does not normalize case,
Unicode or whitespace. Calibration does not reprogram the hardware.

German, English, French and Spanish test languages determine the characters checked.
Success confirms only those characters, not arbitrary Unicode text. French œ/Œ and
Ÿ are outside the Latin-1 sample. Guided QR codes use ISO-8859-1 without ECI. More
options provide custom text up to 1000 characters, UTF-8 with ECI and UTF-8 without
ECI. Oversized QR data and characters outside Latin-1 are rejected. Without ECI,
interpretation depends on the scanner; other sources may use different encodings.

The optional experimental `alt-pair-latin1` profile interprets decimal left-Alt/keypad
sequences as two big-endian ISO-8859-1 bytes. This is not a general Windows Alt-code
decoder. The first byte must be at least 160; CR, LF and Tab are allowed only as the
second byte terminating a scan. Invalid, incomplete or oversized sequences reject
the scan. The `standard` profile does not convert Alt numbers into characters.

Diagnostics show the first unsupported key, modifiers and decoded prefix, along with
unmodified Alt digit sequences. The prefix is not a valid complete scan. Raw data
can be copied. Calibration results and raw events are deleted after at most two
minutes or when explicitly stopping the test.

## Local capture and pause

The **Scan** tab uses only the saved receiver profile. New and queued scans pause
during capture; MQTT, discovery and availability stay connected. A message already
submitted may still arrive. Each completed, nonempty scan, including an undecodable
scan, renews the 120-second deadline. Partial scans do not extend it. Stop or timeout
restores the previous transmission setting; persistently disabled transmission stays
off. Local scans are never added to the outbox.

The last 20 entries remain after stopping, timeout, new capture, calibration and
browser reload. **Clear list** explicitly deletes them. Additional scans evict the
oldest entry. The list is RAM-only and is lost when the receiver reloads or restarts.

## Web access and authentication

Browser setup enables the web interface; terminal setup proposes enabling it too.
Password protection is initially disabled. `0.0.0.0` allows
network access; `127.0.0.1` allows only local access. Recover from an incorrect
restriction with:

```bash
myscanner set web-host 0.0.0.0
```

Passwords require at least eight characters. Storage uses salted PBKDF2-HMAC-SHA256
with 600,000 iterations. With protection enabled, configuration and scan endpoints
require a session; login bootstrap, login and static assets stay public. Sessions
are RAM-only; cookies use HttpOnly and SameSite=Strict. Login and re-authentication
have a global backoff up to five minutes. Password and protection changes revoke sessions.

Automatic logout after 30 minutes without interaction is optional and off by default.
Status polling does not extend it. With the option off, there is no time-based session
limit. Saving normal settings keeps sessions across receiver reloads. Restarting the program ends sessions. The HTTP server does not encrypt
credentials; do not expose it publicly. Shell commands need no web password, but may
require root privileges.

## Development and tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
bash -n install.sh
PYTHONPATH=src python3 tests/mqtt_smoke.py
```

The MQTT test needs Paho and local Mosquitto (`MOSQUITTO_BINARY` can set its path).
Installer tests mock apt/systemd and are not real Linux installation tests. HTTP,
browser and simulated-keystroke tests do not replace testing each actual scanner.

The QR library by Project Nayuki is MIT-licensed; see
[third-party notices](../THIRD_PARTY_NOTICES.md).

## Initial browser setup and removal

New installs default to a browser/terminal choice. `setup_pending` marks an incomplete
configuration: empty broker/device fields are allowed only in this mode, and the web
interface must stay enabled. No MQTT publisher or USB reader starts until a complete,
validated settings save clears the marker. Existing configurations migrate to
`setup_pending=false`; updates preserve them. `myscanner web` prints detected IPv4 URLs.

`myscanner uninstall` confirms either data retention or complete removal. It shares
the installer lock, stops the service before deletion and removes only this program
and, if selected, its configuration/state directories. System packages, Proxmox
assignments and retained Home Assistant discovery are not automatically removed.
