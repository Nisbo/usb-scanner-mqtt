# Give the scanner access in Proxmox

[Back to the guide](../README.md) · [Deutsch](PROXMOX_de.md)

The scanner is connected to the Proxmox server. The scanner program runs **inside a
Debian/Ubuntu VM or LXC**, not on Home Assistant OS. Choose the applicable route
below; you only need one.

## Option A: Linux VM

**In the Proxmox web interface:**

1. Connect the scanner to the Proxmox server.
2. Select your Linux VM.
3. Open **Hardware → Add → USB Device**.
4. Select the scanner by vendor/device ID. If several devices are identical,
   select the appropriate USB port instead.
5. Add it and restart this VM if needed.

**Then, in the Linux VM console:**

```bash
ls -l /dev/input/by-id/
```

Look for your scanner's entry ending in `event-kbd`. It may have a generic name
such as `HIDKeyBoard`. Then run the
[installation command inside this VM](../README.md#start-the-installation).

More information: [official Proxmox USB passthrough documentation](https://github.com/proxmox/pve-docs/blob/master/qm.adoc#usb-passthrough).

## Option B: LXC container

This simple approach uses the `dev0` device passthrough supported by current Proxmox
versions. A dedicated container avoids interrupting unrelated applications on restart.

### 1. On the Proxmox host: find the scanner path

Select the Proxmox node and open its **Shell**, not the container console:

```bash
ls -l /dev/input/by-id/
```

Find the scanner ending in `event-kbd` and note its full path, such as
`/dev/input/by-id/usb-YOUR_SCANNER-event-kbd`. Do not choose a regular keyboard.
If uncertain, compare the list before and after connecting the scanner.

### 2. On the Proxmox host: assign it to the container

**Replace `YOUR_CT_ID` with your container number and the example path with your
actual scanner path. Do not copy these commands unchanged.**

Check existing device assignments first:

```bash
pct config YOUR_CT_ID
```

If `dev0` is not already used:

```bash
pct set YOUR_CT_ID --dev0 path=/dev/input/by-id/usb-YOUR_SCANNER-event-kbd
```

If `dev0` is occupied, choose an unused entry such as `--dev1` rather than overwriting
another device. The [official Proxmox reference](https://github.com/proxmox/pve-docs/blob/master/generated/pct.conf.5-opts.adoc)
describes these `dev[n]` assignments.

Restart **only this container** in the Proxmox interface afterwards. This also
interrupts any other services running in that container.

### 3. Inside the container: check and install

Now open the **container console**:

```bash
ls -l /dev/input/by-id/
```

Check that the assigned scanner path exists there. If only another
`/dev/input/event…` path is visible, check the assignment and select the path
actually available during setup. Then run the
[installation command inside the container](../README.md#start-the-installation).

## Unplugging and restarting

With simple LXC device passthrough, a missing scanner can prevent the container from
starting. Keep it connected during startup. Reconnecting may require a new assignment
or container restart. The scanner receiver alone cannot repair Proxmox passthrough.

VM USB passthrough and LXC device passthrough do not behave identically on unplugging.
These steps do not guarantee failure-proof hotplug.

The scanner installer and uninstaller do not change these Proxmox settings. Remove
an unused assignment separately in Proxmox.
