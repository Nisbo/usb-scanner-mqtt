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

### QR encodings and diagnostics

Test codes support UTF-8 with ECI (default), ISO-8859-1 without ECI and UTF-8 without
ECI. This changes the generated code, not scanner hardware or saved keyboard layout.
ISO-8859-1 rejects unrepresentable characters such as euro signs and emoji. Without
ECI, interpretation depends on the scanner and must be verified on the device.

Diagnostics report the first unsupported key, modifiers and decoded prefix; this
prefix is not a valid complete scan and is never sent as a replacement via MQTT.
Left-Alt sequences show the original keypad digits (including leading zeroes) and
whether Alt was released. No character encoding is inferred and Alt codes are still
rejected by the standard output profile. A copy button handles raw events; unchanged polling
updates preserve text selection. Test results still expire after two minutes.

### Optional packed Alt output profile

The default remains `standard`. Enable the experimental `alt-pair-latin1` profile
only for scanners emitting two packed bytes as one decimal left-Alt/keypad number:

```bash
myscanner set output-profile alt-pair-latin1
```

The GUI exposes the same setting under Setup; save before testing. Keyboard layout
remains independent. Use ISO-8859-1 without ECI for QR tests. The profile explicitly
interprets decimal values as two big-endian ISO-8859-1 bytes. The first byte must
be printable (160 or above); control bytes are rejected except CR/LF/Tab as a second
byte terminating the scan. Normal Enter is supported. Invalid, incomplete or
oversized sequences reject the scan without forwarding partial text. This is not
a general Windows Alt-code decoder and does not reprogram hardware.
Test individual characters, mixed ASCII and then full strings. Automated tests use
simulated input; compatibility must be confirmed on each scanner. Restore the
previous behavior with `myscanner set output-profile standard`.

### Guided calibration

Choose the desired language, start calibration and scan the QR code. If the complete
text matches exactly, apply both detected settings with one click. The language
selects a test character set, not a scanner firmware language setting. German,
English, French and Spanish samples include the Latin alphabet, digits, punctuation
and selected language-specific characters. The exact sample is visible. French
œ/Œ and Ÿ are outside the Latin-1 sample; success confirms only the tested characters,
not arbitrary Unicode support. Case, whitespace and Unicode forms are never normalized.

Calibration evaluates the existing US/German decoders and both output profiles
without changing settings first. It does not add native French/Spanish keyboard
decoders. French/Spanish character samples can match outputs supported through an
existing decoder/profile. Direct key input prefers the standard profile. Ambiguous
or unmatched results cannot be applied; the first differing character is shown when
possible. Expected text is frozen at capture start. Editing it afterwards cannot
turn an incorrect scan into a successful result.

The backend verifies a current, unambiguous result before applying layout and profile
together. Changing the selected language blocks applying the previous result in the
GUI; expiry, abort or a new test invalidate the previous result on the backend.
Test scans are not published over MQTT. Calibration does not reprogram hardware or
confirm processing inside Home Assistant; verify normal scan output there separately.

Guided codes use ISO-8859-1 without ECI. Custom text and alternative QR encodings
remain under additional options. Codes from other sources may use different encodings.

## Local scan view

The Scan tab displays arbitrary consecutive scans using the saved decoder settings,
without an expected-text comparison. Each entry has a copy button. Identical scans
stay separate, leading zeroes are preserved, and at most 20 entries remain in memory.
Undecodable input is shown as an error rather than substituted text.

New and queued scan transmission is paused while MQTT/discovery remain connected.
Previously submitted MQTT messages may still arrive. Each completed, nonempty scan
(including an undecodable scan) renews a 120-second inactivity deadline. Partial input
does not renew it. Stop or expiry restores the prior sending setting; persistently
disabled transmission stays disabled. These local scans never enter the outbox.

Stop, timer expiry, new captures and calibration preserve the scan list. A browser
refresh preserves it too. Clear list explicitly removes entries without changing the
pause or deadline. The last 20 entries are kept; newer scans evict the oldest. The list
is not stored on disk: receiver reload/restart (including configuration changes) loses it. Calibration remains a separate comparison flow; its old plain-test
button is removed. Setup groups scanner identity, display name and topic/generator
under MQTT & Home Assistant; device/decoder settings stay in the scanner section.
