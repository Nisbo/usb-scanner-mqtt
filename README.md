# USB 2 MQTT Scanner

[Deutsch](README_de.md)

Scan a barcode or QR code and receive its contents in Home Assistant.
**Only barcode and QR scanners recognized by Linux as a USB keyboard are supported
(USB HID keyboard mode).** The scanner sends the scanned text as keystrokes.

Example tested with this project: [USB barcode/QR scanner on Amazon Germany
(ASIN B08B5MHK3C)](https://www.amazon.de/dp/B08B5MHK3C?th=1).

Connect the scanner to a Linux computer. At installation, choose browser setup
(recommended) or the terminal wizard.

- [Install and set up](#1-install-and-set-up)
- [Use the web interface](#2-use-the-web-interface)
- [Use it in Home Assistant](#3-use-it-in-home-assistant)
- [Updates and help](#updates-and-help)
- [Change settings through the shell later](#change-settings-through-the-shell-later)
- [Technical background](docs/TECHNICAL.md)

## 1. Install and set up

### What you need

- A USB barcode or QR scanner that works like a keyboard.
- A Linux computer running Debian 12 or newer, or Ubuntu 24.04 or newer.
  Raspberry Pi OS based on Debian 12 (Bookworm) or newer is also expected to work,
  but has **not yet been tested on actual Raspberry Pi hardware**.
  Use the same installation steps below.
  This program is not a Home Assistant add-on and does not install directly on Home Assistant OS.
- An existing MQTT broker: have its address and, if required, username and password
  ready. Home Assistant must connect to the same broker.

Plug the scanner into the Linux computer. In a virtual machine or container,
make the scanner available inside it first. See the
[Proxmox examples for LXC and VM](docs/PROXMOX.md).

### Start the installation

Open a terminal **on the Linux computer connected to the scanner**.
If you are not already logged in as `root`, switch first:

```bash
sudo -i
```

Copy this installation command into the terminal and press Enter:

```bash
wget -qO- https://raw.githubusercontent.com/Nisbo/usb-scanner-mqtt/main/install.sh | bash
```

**First, choose the installer language:**

```text
1. English (default)
2. Deutsch
Language / Sprache [1]:
```

**Press Enter for English, or choose 2 for German.** Menus, questions and hints
then use that language. Without an interactive terminal, English is used. This
choice applies to this run only; browser language detection and the web interface's
own language selector are unchanged.

**Next, choose how you want to set up:**

```text
1. Browser (recommended)
2. Terminal
Choice [1]:
```

**Press Enter to use the browser.** No scanner or MQTT questions follow in the
terminal. After installation, detected IPv4 addresses are displayed, for example:

```text
http://192.168.1.50:8765
```

Open one of the displayed links in a browser on your PC or phone.

Select your scanner and enter the MQTT connection in the browser. Then click
**Save and apply**. Next, check characters with calibration and verify a first scan in Home Assistant as described below.

Choose **2** if you prefer terminal setup. The
[terminal wizard is explained below](#the-terminal-wizard).
Without an interactive terminal, installation automatically prepares browser setup.

The service remains running when you close the terminal and starts again after a
restart of the Linux computer.

## 2. Use the web interface

Use the link displayed by the installer. Run `myscanner web` in the terminal to
show it again later. Addresses have this form:

```text
http://YOUR-LINUX-IP:8765
```

The easiest way is to copy the complete link from `myscanner web`. If you changed
the web port, this command also shows the correct port.

### Initial browser setup

The **Settings** tab opens automatically.

The **Settings** tab has sections for **Scanner**, **MQTT & Home Assistant**, **History & product data**, **Web interface** and **Access protection**. **Save and apply** saves changes from all regular settings sections together. Access protection has its own save button. Device names vary by model: compare the device list before and after plugging in your scanner and click **Search again**. Never select a regular keyboard. If you need a broker first, see the [Home Assistant MQTT guide](https://www.home-assistant.io/integrations/mqtt/).

Follow these steps:

1. Select your scanner under **Detected devices**, not a regular keyboard.
2. Choose a **Display name**. Accents and spaces are allowed, such as `Küche`.
   You can initially keep the suggested technical **Identifier**.
3. Under **MQTT & Home Assistant**, enter the broker's **IP address or hostname only**,
   without `http://`, `https://`, `mqtt://` or an appended port.
4. Enter its port and, if needed, MQTT username and password. Enable **TLS** only
   if the broker provides a TLS connection, commonly on port `8883`. A typical
   connection without TLS uses port `1883`.
5. Initially keep the suggested **Saved keyboard layout**, **Scanner output profile**
   and **Scan topic**. Check characters afterwards with calibration.
6. Click **Save and apply** and wait briefly. Scanner reception and MQTT now start.

### First, check the characters

1. Open **Test & calibration**.
2. Choose the language of the text you want to scan.
3. Click **Start calibration** and scan the displayed QR code.
4. When every character matches, click **Apply detected settings**.

This saves the matching receiver settings. You do not need to understand keyboard
layouts or output profiles first. These test scans are not forwarded to Home Assistant.

For a scanner that reads only linear barcodes, enter the known contents of an
existing barcode under **Custom test text and more options**. Click **Test existing barcode**, then scan your existing barcode; no QR code is needed. Digits alone do not always
identify a keyboard layout unambiguously.

### View and copy any codes

Open **Scan**, click **Start scanning** and scan your codes one after another.
Enable **Look up product data for these local scans** to query products even when automatic lookup is off. This choice is saved in your browser and applies when local scanning starts. It changes neither automatic lookup nor MQTT forwarding.

Each entry has a **Copy** button. Deleting entries or clearing the list requires
confirmation in a dialog. Click **Stop** to resume normal forwarding to Home Assistant.

Forwarding pauses during local capture. After two minutes without another completed
scan, the pause ends automatically.

**Persistent history** also shows normal scans. Each entry is marked **Local**,
**MQTT – queued**, **MQTT – acknowledged by broker**, or **Forwarding disabled**.
Broker acknowledgement does not confirm Home Assistant processing. Calibration
scans are excluded.

The last **1,000 scans** are kept by default, including across updates and restarts.
Change the limit under **Settings → History & product data**. Use **Older entries**
to browse history. Delete individual entries or clear the list explicitly; this
never deletes queued MQTT messages.

### Optionally add product data

Under **Settings → History & product data**:

1. Enable **Look up product data using Open Facts**.
2. Choose a separate **Product data language**, independent of the interface language.
3. Optionally enable **Include product data in MQTT messages**.
4. Keep the **2-second** timeout and click **Save and apply**.

**Enable only when explicitly needed here:** HA List Manager handles its own product lookups. Additional lookups here can cause duplicate requests and request limits. The timeout is the maximum wait for one product response, not an interval between scans.

Lookup is initially disabled. When enabled, numeric codes are sent to Open Food
Facts; arbitrary QR text and URLs are not queried. Non-food products can also be
found. The scan entry shows name, brand, package quantity and product type, with
a large product image viewer inside the page. The image loads only when opened;
use **Close** or **Escape** to dismiss it.

With MQTT enrichment enabled, **the same scan message** additionally contains
`off_status` and `off_data`. Errors, missing products and timeouts still forward
the scan, with `off_data: null`. No second message is sent just to add product data.
Further scans can be read during lookups; a burst can briefly build up the queue.

Found products are cached for **24 hours**, missing products for **one hour**,
separately per language. Up to **15 external lookups within the preceding 60
seconds** are allowed, including directly consecutive lookups. Cache hits do not
count. Only an exhausted budget or a failure triggers a pause. Each entry explains
the reason at the time of that scan; scans are still forwarded. **Clear product cache** forces fresh
lookups once any active pause has ended. Updates and uninstalling with data
retention keep history and cache.

Product data source: [Open Food Facts](https://world.openfoodfacts.org), data under
[ODbL](https://opendatacommons.org/licenses/odbl/1-0/); linked images are subject to
[Open Food Facts terms](https://world.openfoodfacts.org/terms-of-use).

### Change settings

Use **Settings** to change the scanner, MQTT connection or device name.
Then click **Save and apply**. Wait briefly before scanning again.
Leave the new MQTT password field empty to keep the existing password.

**Status** shows whether the scanner and MQTT are connected. You can also turn
scan forwarding off or back on there.

### Password, language and appearance

- **Password protection:** Enable it under **Settings → Access protection**, enter your
  chosen password twice (at least eight characters), and save it separately.
  You can also change the password or turn protection off there.
- **Automatic logout:** Enable it in the same section if wanted. It is initially off.
- **Language:** Choose English or German at the top right. Browser language is used
  initially; your choice is saved in this browser.
- **Light/dark:** Use the sun/moon button at the top right. This choice is also saved in the browser.

Password protection is initially off. The web password is separate from your MQTT
password and is not needed for shell commands. Use the interface on your own trusted
network; the built-in HTTP connection is not encrypted.

## 3. Use it in Home Assistant

1. Make sure Home Assistant's MQTT integration connects to the same broker.
2. Open **Settings → Devices & services → MQTT** and look for the display name
   you chose during setup.
3. Its **Last scan** sensor shows the most recently scanned contents.
4. Stop any active local capture in the **Scan** tab, then scan a normal barcode.
   Check that it arrives in Home Assistant.

QR text can be forwarded too. Long text is available in the sensor's `barcode`
attribute. Every new scan gets a new scan ID, including repeated scans of the same code.

For automations or other applications, see the message format in the
[technical background](docs/TECHNICAL.md#mqtt-and-home-assistant).

### Control directly in Home Assistant

Three switches appear automatically on the scanner device:

| HA switch | Function |
| --- | --- |
| **Scan forwarding** | Turn persistent scan forwarding to MQTT on/off. |
| **Product lookup** | Enable/disable Open Facts lookups. |
| **Include product data** | Include product data in the same MQTT message, or show it only in history. |

Changes are saved and survive restarts. The GUI reflects HA changes automatically,
without overwriting unsaved form edits. GUI changes appear in HA after saving.
Local capture and calibration still pause forwarding even when **Scan forwarding**
is on.

Discovery and states are sent again after updates, HA restarts and MQTT reconnects.
Reinstallation is unnecessary. Switches remain usable with the USB scanner unplugged;
the scan sensor is then unavailable.

### Manually look up a product in HA

Three additional entities appear on the same scanner device:

- **Product query: EAN** – enter and submit a numeric code; leading zeroes are preserved.
- **Product query: Start lookup** – look up the entered EAN.
- **Product query: Result** – product name or lookup status.

Setting the input alone does not start a lookup. Pressing the button works repeatedly
with the same EAN, including when **Product lookup** or **Scan forwarding** is off.
This is an explicitly requested, separate query; it shares the scanner's cache,
product language, timeout and request limits.

Results are **never published to the scan topic** and do not enter scan history.
Other integrations listening for scans will not receive a false scan. Input and
latest result survive restarts. Result attributes include the actually queried
`ean`, `status`, `language`, `cached` and `off_data` containing name, brand, package
quantity and image URL. Editing the input does not change the previous result until
**Start lookup** is pressed. If buttons are pressed rapidly, the newest waiting
request takes precedence.

**Optional: group them on your dashboard.** An entities card provides a separate
frame (for the default identifier `usb-scanner-1`; replace the three entity IDs with the actual IDs shown by Home Assistant):

In your HA dashboard, choose **Edit dashboard → Add card → Manual**, then paste the example below. Find each actual entity ID by opening the entity and its settings on your scanner device. Renaming or name conflicts can change these IDs.

```yaml
type: entities
title: Product query
entities:
  - entity: text.usb_scanner_mqtt_usb_scanner_1_lookup_ean
    name: EAN
  - entity: button.usb_scanner_mqtt_usb_scanner_1_lookup_start
    name: Look up product
  - entity: sensor.usb_scanner_mqtt_usb_scanner_1_lookup_result
    name: Result
  - type: attribute
    entity: sensor.usb_scanner_mqtt_usb_scanner_1_lookup_result
    attribute: ean
    name: Queried EAN
```

### Reuse the scanner ID – even on another computer

The **Identifier** defines the stable HA identity, independently of the display
name and installation. For `kueche`, the suggested entity ID is
`sensor.usb_scanner_mqtt_kueche_last_scan`. On a replacement computer, reuse the
same identifier and MQTT broker. Rename the display name freely. Two scanners
running at the same time must have different identifiers.

## Updates and help

### Update

Run this in the Linux computer's terminal as `root`:

```bash
myscanner update
```

Then reload the browser page with **Ctrl+F5**. Settings and queued MQTT scans are
preserved. Updates run only when you request them.

### Run the installation command again

When an installation or saved settings already exist, the installation command
shows this menu:

| Choice | What happens? |
| --- | --- |
| **1 – Update / repair** (Enter) | Installs the current GitHub version and adds missing packages. Settings, passwords and queued scans are kept. |
| **2 – Reset setup and start again** | Deletes settings, passwords and queued scans after confirmation with `DELETE`. Then choose browser or terminal setup and configure the scanner again. |
| **3 – Uninstall** | Opens the choice described below: keep data or remove everything. |
| **0 – Exit** | Cancels without changing the installation. |

**To test a complete fresh setup, choose 2.** This deletes your previous data.
Proxmox USB passthrough settings are kept.

Choices 1 and 2 restart the service and end web login sessions. Choice 1 keeps
history and product cache; choice 2 deletes them. `myscanner update` still updates directly without this menu. Without an
interactive terminal, the installer keeps existing settings and updates without
questions.

### Uninstall

Run as `root` in the terminal:

```bash
myscanner uninstall
```

Choose **1** to remove the program while keeping settings and queued scans for
reinstallation. **2** also removes those data and stored passwords. **0** cancels.

Confirm removal with `yes` (English) or `ja` (German) when keeping data, or
`DELETE` for complete removal.
The service is stopped first. Shared system packages and Proxmox device passthrough
settings are kept. Remove the old MQTT device in Home Assistant manually if desired.

### Did not enable the web interface?

Run this as `root` in the terminal, then open the browser address above:

```bash
myscanner set gui true
```

### Forgot the web password?

Run this as `root` in the terminal:

```bash
myscanner reset-login
```

This removes only web password protection. Scanner and MQTT settings are preserved.

### Something is not working?

| Problem | First step |
| --- | --- |
| Web interface unavailable | Check the Linux computer's IP address and web port. Enable the interface using the command above if needed. |
| Scanner disconnected | Check USB connection and VM/container device access. Select the correct device in Settings. |
| MQTT disconnected | Check the broker address, port and credentials in Settings. |
| Incorrect characters | Run guided calibration in the browser. |
| Nothing arrives in Home Assistant | Stop local capture and enable forwarding in Status. Check that both programs connect to the same MQTT broker. |

For more information, run:

```bash
myscanner status
```

If asking for help, messages from `myscanner logs` are also useful. Press **Ctrl+C**
to stop displaying them. Do not share passwords or private scan contents.

## Change settings through the shell later

**Optional:** Use this section if you prefer working in the terminal.
For the same changes in your browser, use **Settings** instead.
Run the following commands as `root` on the Linux computer.

Open the browser/terminal choice again:

```bash
myscanner setup
```

Or start the terminal wizard directly:

```bash
myscanner setup --mode shell
```

### The terminal wizard

A value in square brackets is the suggestion; **Enter keeps it**. Existing settings
are proposed when reconfiguring. New installations use the starting values below.

| Question | Meaning and input |
| --- | --- |
| `Scanner device: path or number` | Detected input devices appear above this question with number, name and path. Enter your scanner's number. A single device's path is prefilled. If none are found, a message asks you to check USB/device access. |
| `Scanner ID` | Permanent MQTT and HA identifier; reuse it on a replacement computer. Default `usb-scanner-1`; use unaccented letters, digits, hyphens and underscores. |
| `Name shown in Home Assistant` | Freely chosen display name. `Küche` and spaces work too. |
| `Layout configured ON the scanner` | Starting value `us`, not auto-detected. If unsure, press Enter and calibrate in the browser afterwards. |
| `Output profile` | How additional characters are read. Starts at `standard`, not auto-detected. If unsure, press Enter; calibration checks the profile too. |
| `MQTT scan topic` | Address for scan messages. Suggested from your identifier, such as `usb-scanner-mqtt/usb-scanner-1/scan`. Usually press Enter. |
| `MQTT broker IP or hostname` | Broker IP or hostname only, without `http://`, `https://`, `mqtt://` or a port. |
| `Use TLS?` | Choose `yes` only if your broker provides a TLS connection. Otherwise keep the suggested `no`. |
| `MQTT port` | Commonly `1883` without TLS or `8883` with TLS. Use the port actually configured on the broker. |
| `MQTT username` | Existing broker username. Enter `-` if it requires no login. |
| `MQTT password` | Requested when a username is entered. Input is invisible; this is normal. |
| `Custom CA certificate path` | Only for TLS: leave empty for publicly trusted certificates on first setup; enter `-` to remove a saved CA path. Otherwise enter your custom CA file path. |
| `Enable internal web interface?` | **`yes` is preselected for new setups**. Enter lets you continue in your browser later; `no` leaves it disabled. |
| `Web bind address` | Keep `0.0.0.0` for access from your home network. `127.0.0.1` permits access only on the Linux computer itself. |
| `Web port` | Usually keep `8765`. |
| `Send scans over MQTT?` | **`yes`** for normal forwarding to Home Assistant. |

Reception starts after saving. If the web interface is enabled, the installer
shows browser addresses. Run `myscanner web` to display them again later.

Change individual settings – **replace examples; do not run the entire list**:

| Purpose | Command |
| --- | --- |
| Change broker address | `myscanner set host YOUR-BROKER` |
| Change MQTT username | `myscanner set user YOUR-USERNAME` |
| Change MQTT password | `myscanner set password` – prompts for it without showing input |
| Change device name | `myscanner set name "My Scanner"` |
| Enable / disable web interface | `myscanner set gui true` / `myscanner set gui false` |
| Enable / disable scan forwarding | `myscanner set send true` / `myscanner set send false` |
| Restart the program | `myscanner restart` |

Read scans only in the terminal without forwarding to Home Assistant:

```bash
myscanner test
```

Press **Ctrl+C** to finish. The web interface is temporarily unavailable during this
shell test. A previously running receiver is restarted afterwards.

## Background for interested readers

You do not need to know which Python packages are installed, where files are stored
or how MQTT messages are structured to use the program.
Those details are collected in the [technical background](docs/TECHNICAL.md).

### Access through Nginx (optional)

Configure your domain and the scanner computer’s IP address and web port in Nginx as usual. No extra URL or proxy switch is needed in the scanner program. Use the usual Nginx proxy settings that preserve the original Host. Authentication and change-request checks remain active. Direct home-network access still works.
