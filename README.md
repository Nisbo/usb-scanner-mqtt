# USB Scanner MQTT

[Deutsch](README_de.md)

Connect a USB barcode scanner that emulates a keyboard to MQTT and Home Assistant.
No GUI, desktop session or Home Assistant custom integration is needed.

**Initial version 0.1.0:** one scanner per installation, US/German keyboard layouts,
MQTT 5, Home Assistant discovery and a systemd service. The receiver is separate
from HA List Manager and does not change its files or configuration.

## Install

Run **inside your Debian 12+/Ubuntu 24.04+ machine or LXC**, as root:

```bash
wget -qO- https://raw.githubusercontent.com/Nisbo/usb-scanner-mqtt/main/install.sh | bash
```

The installer downloads the program, checks required packages, installs only missing
packages and asks for the scanner device, name, keyboard layout and MQTT connection.
The password is entered invisibly. Subsequent runs keep your configuration.
The service starts automatically and also starts at boot.

Requirements:

- Linux with systemd, Python 3.11 or newer, and access to the USB input device.
- An existing MQTT broker supporting MQTT 5; none is installed by this project.
- Home Assistant's MQTT integration connected to that broker, if discovery is wanted.

`python3-evdev` and `python3-paho-mqtt` come from your distribution. A private Python
virtual environment uses those apt-managed packages via `--system-site-packages`.
There is no compiler, pip/PyPI dependency download or separate web server to install.

The first installer run needs an interactive terminal (`/dev/tty`). If setup was
interrupted, rerun the installer or run `myscanner setup`.

## Proxmox / LXC

Run the installer **inside the container**, not on the Proxmox host. USB input-device
passthrough must already be configured. The installer does not change Proxmox,
AdGuard, other services or the container configuration, and does not reboot anything.

For the scanner already passed through in our initial test, select:

```text
/dev/input/by-id/usb-TMS_HIDKeyBoard_1234567890abcd-event-kbd
```

Prefer a `/dev/input/by-id/...-event-kbd` path over `event12`, which can change.
An explicitly mapped path such as `/dev/input/barcode-scanner` is also supported.
If your LXC passthrough requires the scanner to be present at container boot, this
installer does not make that passthrough optional. Replugging may require renewing
the host-side mapping. Inside the receiver, missing devices are retried automatically.

## First scan in Home Assistant

1. Run `myscanner status` and check the service is active.
2. In HA, open **Settings → Devices & services → MQTT**. Discovery creates a device
   using your scanner name, with a **Last scan** sensor.
3. Scan a barcode. The sensor state contains the barcode. Attributes contain
   `scan_id`, `scanner`, `timestamp` and the complete `barcode`.
4. Scan the same code again. It receives a **new scan ID**, even if the barcode is equal.

A missing/unreadable scanner is reported as unavailable. No scans are generated
merely by starting the receiver or Home Assistant.

### MQTT format

Default topic: `usb-scanner-mqtt/usb-scanner-1/scan`

```json
{
  "ean": "4062139025398",
  "scanner": "usb-scanner-1",
  "scan_id": "a-unique-id-for-this-scan",
  "timestamp": "2026-11-14T20:00:00+00:00"
}
```

The `ean` field contains the complete scanned text, including QR text. It remains a
string, preserving leading zeroes. The receiver never opens scanned URLs or executes
scanned content. For QR text longer than HA's 255-character state limit, the state
shows `QR scan`; the full content remains in the `barcode` attribute (up to 4096 characters).

For HA List Manager's existing MQTT scanner, select **JSON**, barcode field `ean`,
scanner field `scanner`, expected scanner ID as configured, and scan-ID field `scan_id`.
Do not process this same source simultaneously through a second entity-scanner input.

Discovery and availability messages are retained. **Scan messages are not retained.**
Discovery is announced again after Home Assistant sends its startup message to
`homeassistant/status` (or `<discovery-prefix>/status`). MQTT permissions must permit
publishing the scan, discovery and availability topics and subscribing to that status topic.

## Commands

Run configuration/service commands as root:

```bash
myscanner setup
myscanner set host 192.168.178.170
myscanner set user scanner
myscanner set password
myscanner set layout us
myscanner set name Kitchen
myscanner set topic home/scanner/kitchen/scan
myscanner status
myscanner logs
myscanner test
myscanner restart
myscanner update
```

`set password` asks securely; do not supply the password on the command line.
`ip` is an alias for `host`, and `pw` for `password`. Settings are validated before
saving and restart an already running receiver. `setup` changes the scanner ID too.
Use a different scanner ID/topic on each installation.

`myscanner test` temporarily stops an active receiver, prints scans locally without
sending MQTT, and restarts the receiver when you finish with Ctrl+C. It exclusively
grabs the scanner during the test, so scanner text does not go to another application.
The normal service also uses exclusive input access.

`layout` must match the layout programmed into the scanner. It does not reprogram
the scanner. US/DE letters, digits, common punctuation, Shift, German umlauts and
common AltGr characters are supported. Calibration, arbitrary Unicode input methods,
custom key mappings, multiple scanners in one instance and a GUI are future work.
Unknown key sequences reject the scan instead of silently sending corrupted text.
Enter, keypad Enter and Tab finish a scan. Incomplete input expires after two seconds.

TLS is optional and validates the broker certificate:

```bash
myscanner set tls true
myscanner set port 8883
myscanner set ca-file /etc/usb-scanner-mqtt/broker-ca.pem
```

The example assumes a custom CA; omit `ca-file` when the broker uses a system-trusted
certificate. Do not use TLS with an IP address unless the certificate covers that IP.

## Updates and stored data

`myscanner update` runs the current installer again. Repeating the installation URL
also checks dependencies and service files. Downloads are pinned to a single Git
commit so files from different revisions are not mixed. Current and previous
application revisions are kept; older revisions are removed after a successful update.
Configuration and queued scans are not replaced.

| Location | Contents |
| --- | --- |
| `/etc/usb-scanner-mqtt/config.json` | MQTT credentials and scanner settings; mode 0600 |
| `/var/lib/usb-scanner-mqtt/outbox.sqlite3` | Pending scans; mode 0600 |
| `/opt/usb-scanner-mqtt/` | Application revisions and Python environment |
| `/usr/local/bin/myscanner` | Command wrapper |

Unsent scans are committed to a bounded outbox (maximum 1000 scans) and sent with
MQTT QoS 1. Retries retain the original scan ID, including after a service restart.
MQTT can deliver a message more than once; consumers must deduplicate by scanner
and scan ID. This is not a promise of exactly-once delivery to arbitrary consumers.
At capacity, the receiver reports an error rather than silently deleting old scans.
Broker acknowledgement confirms broker receipt, not completion of a HA action.

The initial service runs as root for input-device access, with systemd filesystem
and capability restrictions. It opens no incoming network port. Logs contain scan
IDs/lengths, not scanned contents or MQTT passwords. The outbox and broker contain
the actual scan text; protect them accordingly.

## Development / handover

- `src/usb_scanner_mqtt/keyboard.py`: key events → complete scan text.
- `receiver.py`: input device, persistent outbox, MQTT/discovery.
- `config.py`: validated atomic configuration writes.
- `cli.py`: setup, settings, local test, service commands and update.
- `install.sh`: repeatable Debian/Ubuntu installation.

Run the standard-library tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The optional integration test `tests/mqtt_smoke.py` requires Paho and a local
Mosquitto executable (`MOSQUITTO_BINARY` can select its path). Mosquitto is a test
dependency only; the installer does not install a broker. Installer tests use an
isolated filesystem and mocked apt/systemd commands. Real USB/LXC operation still
needs to be verified on your actual machine.
