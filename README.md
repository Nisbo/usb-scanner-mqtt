# USB 2 MQTT Scanner

[Deutsch](README_de.md)

Scan a barcode or QR code and receive its contents in Home Assistant.
Connect the scanner to a Linux computer. A setup wizard guides you through the
initial configuration; afterwards, you can change settings in your browser.

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
  This program is not a Home Assistant add-on and does not install directly on Home Assistant OS.
- An existing MQTT broker: have its address and, if required, username and password
  ready. Home Assistant must connect to the same broker.

Plug the scanner into the Linux computer. In a virtual machine or container,
make the scanner available inside it first.

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

**The installer automatically opens an interactive setup wizard.** You do not need
to edit a configuration file or run another list of setup commands afterwards.

### Answer the wizard's questions

A value in square brackets is the suggested value: **press Enter to keep it**.

| Wizard question | What to enter |
| --- | --- |
| `Scanner device: path or number` | Your scanner's number from the displayed device list. Do not choose a regular keyboard. |
| `Scanner ID` | For a single scanner, keep the suggested value with Enter. |
| `Name shown in Home Assistant` | Your preferred device name, for example `Kitchen-Scanner`. |
| `Layout configured ON the scanner`, `Output profile`, `MQTT scan topic` | Keep the suggestions with Enter to get started. Check the characters afterwards using browser calibration. |
| `MQTT broker IP or hostname` | Your existing MQTT broker's address. You do not need to create a new account here. |
| `Use TLS?`, `MQTT port` | Your broker's connection settings. The suggestions suit a typical unencrypted connection on port 1883. |
| `MQTT username` and, if requested, `MQTT password` | Your broker credentials. If it needs no login, enter `-` for the username. Password input is invisible; this is normal. |
| `Enable internal web interface?` | Enter **`yes`** to do subsequent configuration in your browser. Choose `no` for shell-only operation. |
| `Web bind address`, `Web port` | Keep the suggestions with Enter for access from your home network. |
| `Send scans over MQTT?` | **`yes`** to forward normal scans to Home Assistant. |

The program starts automatically at the end. It keeps running after you close the
terminal and starts again when the Linux computer restarts.

Initial setup currently uses this terminal wizard. **If you enabled the web
interface, you do not need the shell commands below for normal settings changes.**

## 2. Use the web interface

Open this address on your PC or phone, replacing `YOUR-LINUX-IP` with the IP address
of the Linux computer connected to the scanner:

```text
http://YOUR-LINUX-IP:8765
```

The MQTT broker may have a different address. If you chose another web port in the
wizard, use that instead of `8765`.

### First, check the characters

1. Open **Test & calibration**.
2. Choose the language of the text you want to scan.
3. Click **Start calibration** and scan the displayed QR code.
4. When every character matches, click **Apply detected settings**.

This saves the matching receiver settings. You do not need to understand keyboard
layouts or output profiles first. These test scans are not forwarded to Home Assistant.

For a scanner that reads only linear barcodes, enter the known contents of an
existing barcode under **Custom test text and more options**. Click **Create QR &
start test**, but then scan your existing barcode. Digits alone do not always
identify a keyboard layout unambiguously.

### View and copy any codes

Open **Scan**, click **Start scanning** and scan your codes one after another.
Each entry has a **Copy** button. Click **Stop** to resume normal forwarding to Home Assistant.

Forwarding is paused during local capture. After two minutes without another
completed scan, the pause ends automatically. The last 20 entries remain available
for copying; **Clear list** explicitly deletes them. Restarting or reloading the
receiver loses this local list, including when saving normal settings.
Reloading the browser page does not delete it.

### Change settings

Use **Setup** to change the scanner, MQTT connection or device name.
Then click **Save and apply**. Wait briefly before scanning again.
Leave the new MQTT password field empty to keep the existing password.

**Status** shows whether the scanner and MQTT are connected. You can also turn
scan forwarding off or back on there.

### Password, language and appearance

- **Password protection:** Enable it under **Setup → Access protection**, enter your
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
2. Find the device named in the setup wizard among the MQTT devices.
3. Its **Last scan** sensor shows the most recently scanned contents.
4. Stop any active local capture in the **Scan** tab, then scan a normal barcode.
   Check that it arrives in Home Assistant.

QR text can be forwarded too. Long text is available in the sensor's `barcode`
attribute. Every new scan gets a new scan ID, including repeated scans of the same code.

For automations or other applications, see the message format in the
[technical background](docs/TECHNICAL.md#mqtt-and-home-assistant).

## Updates and help

### Update

Run this in the Linux computer's terminal as `root`:

```bash
myscanner update
```

Then reload the browser page with **Ctrl+F5**. Settings and queued MQTT scans are
preserved. Updates run only when you request them.

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
| Scanner disconnected | Check USB connection and VM/container device access. Select the correct device in Setup. |
| MQTT disconnected | Check the broker address, port and credentials in Setup. |
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
For the same changes in your browser, use **Setup** instead.
Run the following commands as `root` on the Linux computer.

Run the wizard again, keeping existing values with Enter:

```bash
myscanner setup
```

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
