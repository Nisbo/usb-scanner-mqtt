# USB Scanner MQTT

[Deutsch](README_de.md)

Connect a USB keyboard-emulating barcode/QR scanner to MQTT and Home Assistant.
One scanner per installation, US/German layouts, MQTT 5, discovery and a systemd
service. Configure through the shell or an optional internal web interface.

## Installation

Requirements: Debian 12+/Ubuntu 24.04+, Python 3.11+, systemd, input-device access,
and an existing MQTT 5 broker. Run as root on the target Linux machine:

```bash
wget -qO- https://raw.githubusercontent.com/Nisbo/usb-scanner-mqtt/main/install.sh | bash
```

The installer installs missing distribution packages, runs interactive setup and
starts the service. Password input is hidden. Repeated installation and explicit
updates preserve configuration and queued scans. The URL installs the published
`main` revision. No automatic updates are enabled.

`python3-evdev` and `python3-paho-mqtt` are apt-managed, used through a Python venv
with `--system-site-packages`. No compiler, pip download or separate web server is needed.

For containers/VMs, configure input-device passthrough separately. The installer does
not change host/container settings. Prefer `/dev/input/by-id/...-event-kbd` over
changing `eventN` paths. Container boot without the device and USB hotplug depend on
passthrough configuration; the receiver itself retries missing devices.

## Shell and optional web interface

```bash
myscanner setup
myscanner set gui true
myscanner set web-host 0.0.0.0
myscanner set web-port 8765
myscanner set send false
myscanner status
myscanner test
myscanner logs
myscanner restart
myscanner update
```

Shell setup remains fully supported and asks whether to enable the GUI and scan
sending. The GUI is disabled by default. When enabled, open
`http://<linux-address>:8765`. There is **no login**: use only on a trusted internal
network, with no public port forwarding. Binding to `127.0.0.1` permits only browsers
on the Linux machine itself and removes remote access. Recover through the shell
with `myscanner set web-host 0.0.0.0`. Styled dialogs warn before changing web access.
`myscanner set gui false` disables the interface while reception/MQTT continue.

The GUI provides settings, scanner/MQTT connectivity, queue size, last-scan time,
local scan testing and layout calibration. Blank password fields preserve the stored
password. CLI and GUI share validated configuration. Saving reloads the receiver;
do not scan during that brief interruption. Address/port changes require opening
the new URL. Re-enable a disabled GUI through the shell.

### Disable scan sending for testing

`myscanner set send false` or the GUI switch persistently disables **scan** sending,
including after restart. New test scans are discarded and will not be replayed.
Existing queued scans remain intact and paused. A message already handed to MQTT
may still arrive. Discovery and availability continue. Explicitly re-enable with
`myscanner set send true` when finished.

The combined **Test & calibration** page automatically pauses scan transmission;
MQTT and discovery stay connected. The first scan, explicit stop or a two-minute
timeout restores the previous transmission state. Persistently disabled sending
stays disabled. A message handed to MQTT before the test may still arrive. Test
scans never enter the outbox; existing scans stay intact. Results remain in memory
until the original two-minute deadline; explicit stop clears them immediately.

The separate `myscanner test` command temporarily stops an active receiver, prints
scans locally without MQTT and restarts the previously active service on Ctrl+C.
The GUI is also unavailable during that shell test.

### Calibration

Enter known text and generate a QR code locally in the browser. The combined button
also starts capture; a plain scan test works with existing 1D barcodes. Up to 1000
characters may be entered; UTF-8 texts exceeding QR capacity are rejected visibly.

The interface compares US/German interpretations to the expected text. Switch the
preview layout without rescanning; only saving applies it to normal reception.
The keyboard view highlights physical key codes including Shift/AltGr and labels
them for the selected layout. Y/Z and punctuation distinguish layouts better than
digits. The receiver does not reprogram the scanner or recover information already
lost inside it. Custom key mappings and other layouts are not included yet.

Device setup offers a dropdown and manual path entry. A button generates the standard
scan topic from the scanner ID. Leading/trailing slashes change MQTT topic identity;
the generator does not add them.

## MQTT settings and Home Assistant

```bash
myscanner set host broker.example.net
myscanner set user scanner
myscanner set password
myscanner set layout us
myscanner set name Scanner
myscanner set tls true
myscanner set port 8883
myscanner set ca-file /etc/usb-scanner-mqtt/broker-ca.pem
```

Passwords are prompted securely, never supplied as arguments. `ip`/`pw` alias
`host`/`password`. TLS validates the certificate; a custom CA file is optional.
Changes restart a running service.

Connect Home Assistant's MQTT integration to the broker. Discovery creates a device
with the configured name and a **Last scan** sensor. Attributes are `barcode`,
`scanner`, `scan_id` and `timestamp`. States longer than 255 characters display
`QR scan`; the complete content stays in the attribute. Maximum scan length: 4096.

Default topic: `usb-scanner-mqtt/usb-scanner-1/scan`

```json
{"ean":"0012345678905","scanner":"usb-scanner-1","scan_id":"unique-scan-id","timestamp":"2026-01-01T12:00:00+00:00"}
```

`ean` is a string, including QR text and leading zeroes. Each completed new scan has
a fresh ID, even for identical contents. Retries preserve their ID and original topic.
MQTT 5, QoS 1, **non-retained scans**. Consumers must deduplicate by scanner and scan ID.
Broker acknowledgement does not confirm processing in Home Assistant.

Discovery/availability are retained. HA birth at `<discovery_prefix>/status`
(default `homeassistant/status`) re-announces discovery without replaying scans.
ACLs must allow these publications and the birth subscription. Availability requires
both an open input device and broker connectivity.

For HA List Manager, configure its JSON MQTT scanner with barcode field `ean`,
scanner field `scanner`, and scan-ID field `scan_id`. Use only one scanner source
for the same messages.

## Operation and storage

A persistent FIFO holds up to 1000 scans during MQTT outages. A full queue reports
an error without displacing existing scans. This protects against MQTT outages;
an offline Home Assistant can still miss non-retained messages.

| Location | Contents |
| --- | --- |
| `/etc/usb-scanner-mqtt/config.json` | Settings/credentials, mode 0600 |
| `/var/lib/usb-scanner-mqtt/outbox.sqlite3` | Pending scans, mode 0600 |
| `/opt/usb-scanner-mqtt/` | Current/previous revision and Python environment |

The service runs as root for input access, with systemd restrictions. Configuration
and state directories are writable for GUI configuration. Normal logs omit scan
contents/passwords. MQTT, the outbox and explicit tests contain actual scan contents.
Scanned text is never executed; scanned URLs are never opened.

US/German layouts support Shift, Caps and common AltGr characters. Enter, keypad
Enter and Tab finish scans. Unknown sequences reject the scan; partial scans expire
after two seconds. Multiple scanners per service and automatic cleanup of old
discovery entities are not implemented.

## Development and tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
bash -n install.sh
PYTHONPATH=src python3 tests/mqtt_smoke.py
```

The optional MQTT test needs Paho and a local Mosquitto executable; select its path
with `MOSQUITTO_BINARY`. The installer does not install a broker. Installer tests
mock apt/systemd and are not real Linux installation tests. HTTP tests use a local
test server and do not replace hardware testing.

The bundled QR generator by Project Nayuki is MIT-licensed; see
[third-party notices](THIRD_PARTY_NOTICES.md) for source and license information.
