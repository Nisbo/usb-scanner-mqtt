# Technischer Hintergrund

[Zur einfachen Anleitung](../README_de.md) · [English](TECHNICAL.md)

Diese Informationen ergänzen die Bedienungsanleitung. Für Installation und normale
Bedienung ist es nicht nötig, sie durchzuarbeiten.

## Installation und Dateien

Der Installer unterstützt Debian 12+/Ubuntu 24.04+ mit systemd und Python 3.11+.
Er installiert fehlende Pakete über apt: `ca-certificates`, `curl`, `python3`,
`python3-venv`, `python3-evdev` und `python3-paho-mqtt`. Die eigene Python-Umgebung
nutzt die Distributionspakete mit `--system-site-packages`; es werden weder ein
Compiler noch pip-Downloads, ein MQTT-Broker oder ein separater Webserver benötigt.

Downloads sind an einen Git-Commit gebunden, damit ein Update keine Revisionen
mischt. Die aktuelle und vorherige Programmrevision bleiben erhalten. Wiederholtes
Installieren und Updates erhalten Konfiguration und persistente Outbox. Bei einem
unmittelbaren Fehler des Dienstneustarts wird die vorherige Anwendung nach Möglichkeit
wiederhergestellt; das ist kein vollständiges Rollback der Paketinstallation.

| Pfad | Inhalt |
| --- | --- |
| `/etc/usb-scanner-mqtt/config.json` | Einstellungen und Zugangsdaten, Dateimodus 0600 |
| `/var/lib/usb-scanner-mqtt/outbox.sqlite3` | Wartende MQTT-Scans, Dateimodus 0600 |
| `/opt/usb-scanner-mqtt/` | Programmrevisionen und Python-Umgebung |
| `/usr/local/bin/myscanner` | Shell-Befehl |

Der Dienst läuft für den Gerätezugriff als root mit systemd-Beschränkungen.
Die Einstellungen und das Zustandsverzeichnis sind beschreibbar. Normale Logs
enthalten keine Passwörter oder Scantexte. Explizite Tests, MQTT-Nachrichten und
Outbox enthalten die tatsächlichen Inhalte. Gescannte Texte werden niemals als
Befehle ausgeführt; gescannte URLs werden nicht automatisch geöffnet.

## Gerätezugriff und Grenzen

Es wird ein Scanner je Installation unterstützt. Mehrere parallele Scanner und das
automatische Entfernen veralteter Home-Assistant-Discovery-Einträge sind noch nicht umgesetzt.

Ein stabiler Pfad wie `/dev/input/by-id/…-event-kbd` ist einer wechselnden
`eventN`-Nummer vorzuziehen. In VMs/Containern muss das Eingabegerät separat
freigegeben sein. Der Installer verändert keine Host-/Containerkonfiguration.
Ob ein Container ohne Scanner startet und wie Hotplug funktioniert, hängt von dieser
Freigabe ab. Der Empfänger versucht fehlende Geräte wieder zu öffnen.

## MQTT und Home Assistant

Die Verbindung verwendet MQTT 5. Standard-Topic:

```text
usb-scanner-mqtt/usb-scanner-1/scan
```

Beispiel einer Scan-Nachricht:

```json
{"ean":"0012345678905","scanner":"usb-scanner-1","scan_id":"unique-scan-id","timestamp":"2026-01-01T12:00:00+00:00"}
```

- `ean` bleibt ein String, auch bei QR-Text und führenden Nullen.
- Jeder neue abgeschlossene Scan erhält eine neue ID, auch bei gleichem Inhalt.
- Wiederholungen derselben wartenden Nachricht behalten ID und ursprüngliches Topic.
- Scans werden mit QoS 1 und **ohne Retain** gesendet. Empfänger sollten nach
  Scannerkennung und Scan-ID deduplizieren; es gibt keine pauschale Exactly-once-Zusage.
- Eine Broker-Bestätigung bestätigt nicht die Verarbeitung in Home Assistant.

Bis zu 1000 ausstehende Scans werden dauerhaft gespeichert. Bei voller Outbox wird
ein Fehler gemeldet; vorhandene Einträge werden nicht verdrängt. Die Outbox schützt
vor MQTT-Ausfällen. Wenn Home Assistant bei verbundenem Broker offline ist, kann es
nicht gespeicherte MQTT-Nachrichten trotzdem verpassen.

Discovery und Verfügbarkeit werden retained gesendet. HA-Birth auf
`<discovery_prefix>/status` (standardmäßig `homeassistant/status`) löst die erneute
Discovery-Veröffentlichung aus, ohne alte Scans erneut zu senden. Brokerrechte
müssen diese Veröffentlichungen und das Abonnement erlauben. Der Scanner gilt als
verfügbar, wenn das Eingabegerät geöffnet und MQTT verbunden ist.

Der Sensor **Last scan** enthält die Attribute `barcode`, `scanner`, `scan_id` und
`timestamp`. Bei Text über 255 Zeichen lautet sein Zustand `QR scan`; der volle Text
bleibt im Attribut `barcode`. Die maximale Scanlänge beträgt 4096 Zeichen.

Für HA List Manager: JSON-MQTT-Scanner verwenden, Barcode-Feld `ean`,
Scannerkennungsfeld `scanner`, Scan-ID-Feld `scan_id`. Dieselben Nachrichten nur
über eine Scannerquelle verarbeiten.

## Empfang und Kalibrierung

Unterstützte Tastaturlayouts: US, Deutsch, britisches Englisch, Französisch (AZERTY)
und Spanisch. Shift, Caps und häufige AltGr-Zeichen werden ausgewertet;
französische und spanische Akzentfolgen werden unterstützt. Enter, Nummernblock-Enter
und Tab schließen Scans ab. Unbekannte Sequenzen verwerfen den Scan. Unvollständige
Eingaben verfallen nach zwei Sekunden; es werden keine Teiltexte als Ersatz gesendet.

Die Kalibrierung vergleicht alle fünf Layouts und beide Ausgabeprofile mit einem
bekannten Solltext. Bei direkter Tasteneingabe wird das Standardprofil bevorzugt.
Nur ein aktueller, eindeutiger, zeichengetreuer Treffer kann übernommen werden.
Groß-/Kleinschreibung, Unicode und Leerraum werden beim Vergleich nicht normalisiert.
Die Kalibrierung programmiert die Hardware nicht um.

Die Testsprachen Deutsch, Englisch, Französisch und Spanisch bestimmen die geprüften
Zeichen. Ein erfolgreicher Test bestätigt nur diese Zeichen, keine beliebigen
Unicode-Texte. Französische Ligaturen œ/Œ und Ÿ sind im Latin-1-Test nicht enthalten.
Geführte QR-Codes verwenden ISO-8859-1 ohne ECI. Weitere Optionen bieten eigene Texte
bis 1000 Zeichen, UTF-8 mit ECI und UTF-8 ohne ECI. Zu große QR-Inhalte und nicht in
Latin-1 darstellbare Zeichen werden abgelehnt. Ohne ECI hängt die Interpretation
vom Scanner ab; andere Quellen können anders kodiert sein.

Das optionale experimentelle Profil `alt-pair-latin1` interpretiert eine dezimale
linke-Alt-/Nummernblock-Sequenz als zwei Big-Endian-ISO-8859-1-Bytes. Es ist kein
allgemeiner Windows-Alt-Code-Decoder. Das erste Byte muss mindestens 160 sein;
CR, LF und Tab sind nur als zweites Byte für den Scanabschluss erlaubt. Ungültige,
unvollständige oder zu lange Sequenzen verwerfen den Scan. Das Standardprofil
`standard` wandelt Alt-Zahlen nicht in Zeichen um.

Diagnosen zeigen erste nicht unterstützte Taste, Modifier und decodierten Anfang
sowie die unveränderten Alt-Ziffernfolgen. Der Anfang ist kein gültiger Gesamtscan.
Rohdaten können kopiert werden. Ergebnisse und Rohdaten der Kalibrierung werden
nach spätestens zwei Minuten bzw. beim expliziten Beenden gelöscht.

## Lokale Aufnahme und Pause

Im Tab **Scannen** gilt ausschließlich das gespeicherte Empfangsprofil. Neue und
wartende Scans pausieren während der Aufnahme; MQTT, Discovery und Verfügbarkeit
bleiben verbunden. Eine vorher übergebene Nachricht kann noch ankommen. Jeder
abgeschlossene, nicht leere Scan, auch ein nicht decodierbarer, erneuert die
120-Sekunden-Frist. Teilscans verlängern sie nicht. Beenden oder Ablauf stellt die
vorherige Versandeinstellung wieder her; dauerhaft ausgeschalteter Versand bleibt aus.
Lokale Scans werden nicht in die Outbox aufgenommen.

Die letzten 20 Einträge bleiben bei Beenden, Ablauf, neuer Aufnahme, Kalibrierung und
Browser-Neuladen erhalten. **Liste leeren** löscht sie ausdrücklich. Weitere Scans
verdrängen den ältesten Eintrag. Die Liste liegt nur im RAM und geht beim Neuladen
oder Neustarten des Empfangsdienstes verloren.

## Webzugriff und Zugangsschutz

Browser-Einrichtung schaltet die Weboberfläche ein; der Terminal-Assistent schlägt
sie ebenfalls vor. Der Passwortschutz ist zunächst ausgeschaltet. `0.0.0.0` erlaubt
Netzwerkzugriff; `127.0.0.1` nur lokalen Zugriff. Nach falscher Einschränkung hilft:

```bash
myscanner set web-host 0.0.0.0
```

Passwörter haben mindestens acht Zeichen. Gespeichert wird ein gesalzener
PBKDF2-HMAC-SHA256-Hash mit 600.000 Iterationen. Bei aktiviertem Schutz benötigen die
Konfigurations- und Scan-Endpunkte eine Sitzung; Login-Bootstrap, Login und statische
Dateien bleiben öffentlich. Sitzungen liegen im RAM; Cookies nutzen HttpOnly und
SameSite=Strict. Login und erneute Passwortprüfung haben einen globalen Backoff
bis fünf Minuten. Passwortänderung und Änderungen am Schutz widerrufen Sitzungen.

Automatische Abmeldung nach 30 Minuten ohne Bedienung ist optional, standardmäßig
aus. Statuspolling verlängert die Frist nicht. Ohne diese Option gibt es kein
zeitgesteuertes Sitzungslimit. Neuladen/Neustarten des Dienstes beendet Sitzungen.
Der HTTP-Server verschlüsselt Zugangsdaten nicht; kein öffentlicher Internetzugriff.
Shell-Befehle benötigen das Web-Passwort nicht, aber gegebenenfalls root-Rechte.

## Entwicklung und Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
bash -n install.sh
PYTHONPATH=src python3 tests/mqtt_smoke.py
```

Der MQTT-Test braucht Paho und ein lokales Mosquitto (`MOSQUITTO_BINARY` kann dessen
Pfad setzen). Installer-Tests verwenden nachgebildete apt-/systemd-Befehle und
ersetzen keinen Linux-Installationstest. HTTP-/Browser-Tests und simulierte
Tastensequenzen ersetzen keinen Test mit dem jeweiligen echten Scanner.

Die QR-Bibliothek von Project Nayuki steht unter MIT-Lizenz; siehe
[Drittanbieterhinweise](../THIRD_PARTY_NOTICES.md).

## Browser-Ersteinrichtung und Deinstallation

Neue Installationen bieten Browser/Terminal zur Wahl. `setup_pending` kennzeichnet
eine unvollständige Konfiguration: Nur dann dürfen Broker und Gerät noch leer sein,
und die Weboberfläche muss aktiv sein. MQTT-Publisher und USB-Leser starten erst
nach vollständigem, validiertem Speichern. Bestehende Konfigurationen werden als
`setup_pending=false` gelesen; Updates erhalten sie. `myscanner web` zeigt IPv4-URLs.

`myscanner uninstall` lässt Datenerhalt oder vollständige Entfernung bestätigen.
Es verwendet dieselbe Sperre wie der Installer, stoppt vor dem Löschen den Dienst
und entfernt nur das Programm sowie auf Wunsch dessen Konfigurations-/Zustandsordner.
Systempakete, Proxmox-Zuordnungen und retained HA-Discovery werden nicht automatisch entfernt.
