# Scanner unter Proxmox freigeben

[Zur Anleitung](../README_de.md) · [English](PROXMOX.md)

Der Scanner steckt am Proxmox-Server. Das Scannerprogramm läuft **in einer eigenen
Debian-/Ubuntu-VM oder einem LXC**, nicht auf Home Assistant OS. Wähle unten den
passenden Weg. Du brauchst nur einen davon.

## Variante A: Linux-VM

**In der Proxmox-Weboberfläche:**

1. Scanner an den Proxmox-Server anschließen.
2. Deine Linux-VM auswählen.
3. **Hardware → Hinzufügen → USB-Gerät** öffnen.
4. Den Scanner über Hersteller-/Geräte-ID auswählen. Bei mehreren identischen
   Geräten stattdessen den passenden USB-Port wählen.
5. Hinzufügen und die VM gegebenenfalls gezielt neu starten.

**Danach in der Konsole der Linux-VM:**

```bash
ls -l /dev/input/by-id/
```

Suche den Eintrag deines Scanners mit der Endung `event-kbd`. Ein generischer Name
wie `HIDKeyBoard` ist möglich. Anschließend den
[Installationsbefehl in dieser VM ausführen](../README_de.md#installation-starten).

Weitere Informationen: [offizielle Proxmox-Dokumentation zu USB-Passthrough](https://github.com/proxmox/pve-docs/blob/master/qm.adoc#usb-passthrough).

## Variante B: LXC-Container

Diese einfache Variante verwendet die Gerätefreigabe `dev0` aktueller Proxmox-Versionen.
Ein eigener Container vermeidet, dass ein nötiger Neustart andere Anwendungen unterbricht.

### 1. Auf dem Proxmox-Host: Scannerpfad finden

Wähle den Proxmox-Knoten und öffne dessen **Shell**, nicht die Container-Konsole:

```bash
ls -l /dev/input/by-id/
```

Suche den Scanner mit der Endung `event-kbd` und notiere den vollständigen Pfad,
etwa `/dev/input/by-id/usb-DEIN_SCANNER-event-kbd`.
Wähle keine normale Tastatur. Wenn du unsicher bist, vergleiche die Liste vor und
nach dem Anstecken des Scanners.

### 2. Auf dem Proxmox-Host: dem Container zuordnen

**Ersetze `DEINE_CT_ID` durch die Nummer deines Containers und den Beispielpfad
durch deinen tatsächlichen Scannerpfad. Nicht unverändert kopieren.**

Prüfe zuerst die vorhandenen Gerätezuordnungen:

```bash
pct config DEINE_CT_ID
```

Wenn noch kein `dev0` verwendet wird:

```bash
pct set DEINE_CT_ID --dev0 path=/dev/input/by-id/usb-DEIN_SCANNER-event-kbd
```

Ist `dev0` schon belegt, verwende einen freien Eintrag wie `--dev1`, statt ein
anderes Gerät zu überschreiben. Die
[offizielle Proxmox-Referenz](https://github.com/proxmox/pve-docs/blob/master/generated/pct.conf.5-opts.adoc)
beschreibt diese `dev[n]`-Zuordnungen.

Starte anschließend **nur diesen Container** über die Proxmox-Oberfläche neu.
Dabei werden gegebenenfalls auch andere Dienste in diesem Container unterbrochen.

### 3. Im Container: prüfen und installieren

Öffne jetzt die **Konsole des Containers**:

```bash
ls -l /dev/input/by-id/
```

Prüfe, dass der freigegebene Scannerpfad dort vorhanden ist. Ist nur ein anderer
`/dev/input/event…`-Pfad sichtbar, prüfe die Zuordnung und wähle den tatsächlich
verfügbaren Pfad bei der Einrichtung. Anschließend den
[Installationsbefehl im Container ausführen](../README_de.md#installation-starten).

## Wichtig beim Abziehen und Neustarten

Mit der einfachen LXC-Gerätefreigabe kann ein fehlender Scanner den Containerstart
verhindern. Lass ihn für den Start angeschlossen. Nach erneutem Anstecken kann eine
erneute Zuordnung oder ein Container-Neustart nötig sein. Der Scannerempfänger
allein kann diese Proxmox-Freigabe nicht reparieren.

Die VM-USB-Freigabe und die LXC-Gerätefreigabe verhalten sich beim Abziehen nicht
identisch. Die Schritte oben sind keine Zusage für ausfallsicheres Hotplug.

Das Installations- oder Deinstallationsscript des Scannerprogramms ändert diese
Proxmox-Einstellungen nicht. Entferne eine nicht mehr benötigte Freigabe in Proxmox separat.
