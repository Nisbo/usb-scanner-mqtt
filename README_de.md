# USB Scanner MQTT

[English](README.md)

USB-Barcodescanner mit Tastaturemulation an MQTT und Home Assistant anbinden.
Ohne GUI und ohne geöffnetes Terminal oder Dashboard im laufenden Betrieb.

**Erster Stand 0.1.0:** ein Scanner pro Installation, deutsches und US-Tastaturlayout,
MQTT 5, MQTT Discovery und automatischer Start über systemd. Eigenständiges Projekt;
HA List Manager wird nicht verändert.

## Installation

**Im Debian-12+/Ubuntu-24.04+-Container bzw. Linux-Rechner als root ausführen:**

```bash
wget -qO- https://raw.githubusercontent.com/Nisbo/usb-scanner-mqtt/main/install.sh | bash
```

Der Installer installiert nur fehlende Pakete und fragt Scannergerät, Scannerkennung,
Anzeigename, Tastaturlayout und MQTT-Verbindung ab. Das Passwort wird verdeckt
abgefragt. Der Dienst wird eingerichtet und automatisch gestartet. Vorhandene
Einstellungen bleiben bei erneutem Aufruf erhalten. Es erfolgt kein Neustart des
Containers oder Rechners.

Voraussetzung: Linux mit systemd, Python ab 3.11, Zugriff auf den Scanner und ein
bereits vorhandener MQTT-Broker mit MQTT-5-Unterstützung. Für Discovery muss die
MQTT-Integration in HA mit diesem Broker verbunden sein.

Paho und evdev werden als Debian-/Ubuntu-Pakete installiert. Eine eigene Python-
Umgebung nutzt diese Pakete mit `--system-site-packages`. Kein Compiler, kein
pip-/PyPI-Download und kein zusätzlicher Webserver erforderlich.

## Dein Proxmox-LXC

Die Installation gehört **in den Container**, nicht auf den Proxmox-Host. Die
Gerätedurchreichung muss bereits funktionieren. Der Installer verändert weder
AdGuard noch Proxmox oder die LXC-Konfiguration.

Für den bereits getesteten Scanner:

```text
/dev/input/by-id/usb-TMS_HIDKeyBoard_1234567890abcd-event-kbd
```

Im Setup kannst du das Gerät aus einer nummerierten Liste wählen. Ein fester
`by-id`-Pfad ist besser als eine wechselnde Nummer wie `event12`.

**Wichtig:** Die vorhandene Proxmox-Freigabe wird dadurch nicht optional. Falls
Container 301 ohne angeschlossenen Scanner bisher nicht starten kann, bleibt das
eine getrennte Proxmox-Einstellung. Auch erneutes Einstecken kann dort eine neue
Freigabe benötigen. Der Empfangsdienst selbst wartet auf ein fehlendes Gerät.

## Ersten Scan in HA prüfen

```bash
myscanner status
```

In HA unter **Einstellungen → Geräte & Dienste → MQTT** erscheint das Gerät unter
seinem konfigurierten Namen. Der Sensor **Last scan** zeigt den letzten Barcode;
in den Attributen stehen `scan_id`, `scanner`, `timestamp` und `barcode`.

Zweimal denselben Barcode scannen erzeugt zwei verschiedene Scan-IDs. Beim Start
von HA oder des Dienstes wird kein alter Scan neu erzeugt. Fehlt der Scanner oder
kann er nicht gelesen werden, ist das Gerät nicht verfügbar.

Standard-Topic: `usb-scanner-mqtt/usb-scanner-1/scan`

```json
{
  "ean": "4062139025398",
  "scanner": "usb-scanner-1",
  "scan_id": "eindeutige-id-pro-scan",
  "timestamp": "2026-11-14T20:00:00+00:00"
}
```

In HA List Manager einen MQTT-Scanner mit **JSON** anlegen: Barcode-Feld `ean`,
Scannerkennungsfeld `scanner`, erwartete Kennung wie im Setup, Scan-ID-Feld `scan_id`.
Nicht denselben Scan gleichzeitig zusätzlich über einen Entitätsscanner verarbeiten.

Discovery und Verfügbarkeit werden mit Retain gesendet, **Scans ohne Retain**.
Auch QR-Text wird übertragen; URLs werden niemals geöffnet oder ausgeführt.
Lange Inhalte stehen vollständig im Attribut `barcode` (maximal 4096 Zeichen).
Ab 256 Zeichen zeigt der HA-Sensor als Zustand nur `QR scan`.

## Einstellungen und Tests

```bash
myscanner setup
myscanner set host 192.168.178.170
myscanner set user scanner
myscanner set password
myscanner set layout us
myscanner set name Küchenscanner
myscanner status
myscanner logs
myscanner test
myscanner restart
myscanner update
```

`set password` fragt das Passwort verdeckt ab. Nicht als Kommandozeilenargument
angeben. `ip` geht auch statt `host`, `pw` statt `password`. Ein laufender Dienst
wird nach einer gültigen Einstellungsänderung neu gestartet.

`myscanner test` stoppt einen laufenden Empfänger vorübergehend und zeigt Scans
lokal an, ohne MQTT-Nachrichten zu senden. Mit **Strg+C** beenden; danach wird der
vorher aktive Dienst wieder gestartet. Das Scannergerät wird exklusiv gelesen.

Das Layout muss zur Einstellung **am Scanner** passen. `layout us` programmiert
den Scanner nicht um. Unterstützt werden US/DE-Zeichen, Ziffern, übliche
Sonderzeichen, Shift, deutsche Umlaute und häufige AltGr-Zeichen. Enter, Nummernblock-
Enter oder Tab schließen einen Scan ab. Unvollständige Eingaben verfallen nach zwei
Sekunden. Unbekannte Tastensequenzen verwerfen den Scan, statt falschen Text zu senden.
Kalibrierung, freie Tastenkorrekturen, mehrere Scanner pro Instanz und GUI kommen später.

Optionales TLS mit Zertifikatsprüfung:

```bash
myscanner set tls true
myscanner set port 8883
myscanner set ca-file /etc/usb-scanner-mqtt/broker-ca.pem
```

Die CA-Datei ist nur für eine eigene Zertifizierungsstelle nötig. Bei öffentlich
vertrauenswürdigen Zertifikaten genügt der System-Zertifikatsspeicher.

## Updates und Speicherung

`myscanner update` oder erneutes Aufrufen der Installations-URL prüft die Installation
und aktualisiert sie. Zugangsdaten und wartende Scans bleiben erhalten. Es bleiben
höchstens der aktuelle und vorherige Programmstand gespeichert.

- Einstellungen: `/etc/usb-scanner-mqtt/config.json`, nur für root lesbar (0600).
- Wartende Scans: `/var/lib/usb-scanner-mqtt/outbox.sqlite3`, ebenfalls 0600.
- Programm und Python-Umgebung: `/opt/usb-scanner-mqtt/`.

Bis zu 1000 ausstehende Scans werden dauerhaft zwischengespeichert. Bei erneuter
Übertragung bleibt die Scan-ID gleich. MQTT QoS 1 kann dennoch doppelt zustellen;
der Empfänger muss anhand von Scannerkennung und Scan-ID deduplizieren. Eine
Broker-Bestätigung bedeutet nicht, dass eine Aktion in HA schon abgeschlossen ist.
Bei voller Warteschlange wird ein Fehler gemeldet; alte Scans werden nicht still gelöscht.

In dieser ersten Version läuft der Dienst für den Gerätezugriff als root, mit
systemd-Beschränkungen für Dateisystem und Berechtigungen. Er öffnet keinen Webport.
Scaninhalte und Passwörter werden nicht ins normale Log geschrieben. MQTT und die
Warteschlange enthalten dagegen die echten Scaninhalte.

Für Entwicklung, Tests und Übergabe siehe [englische README](README.md#development--handover).
Die Installer-Abläufe wurden isoliert mit nachgebildeten Systembefehlen geprüft;
der echte Installations- und Hardwaretest auf deinem LXC steht noch aus.
