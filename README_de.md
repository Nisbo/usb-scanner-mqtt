# USB Scanner MQTT

[English](README.md)

USB-Barcode- und QR-Scanner mit Tastaturemulation an MQTT und Home Assistant anbinden.
Ein Scanner pro Installation, US-/DE-Tastaturlayout, MQTT 5 und automatische
Home-Assistant-Erkennung. Einrichtung per Shell oder optionaler interner Weboberfläche.

## Installation

Voraussetzungen: Debian 12+/Ubuntu 24.04+, Python 3.11+, systemd, Zugriff auf das
USB-Eingabegerät und ein vorhandener MQTT-5-Broker.

Als root auf dem Linux-Zielsystem ausführen:

```bash
wget -qO- https://raw.githubusercontent.com/Nisbo/usb-scanner-mqtt/main/install.sh | bash
```

Der Installer installiert nur fehlende Distributionspakete, richtet den Dienst ein
und startet das Shell-Setup. Das Passwort wird verdeckt abgefragt. Erneutes Ausführen
erhält die Konfiguration und wartende Scans. Updates erfolgen ausdrücklich, nicht automatisch.
Die Installations-URL lädt den veröffentlichten Stand von `main`.

`python3-evdev` und `python3-paho-mqtt` werden über apt verwaltet. Die Python-Umgebung
nutzt sie mit `--system-site-packages`; Compiler, pip-Downloads und ein zusätzlicher
Webserver sind nicht erforderlich.

In VMs/Containern muss der Zugriff auf das Eingabegerät separat eingerichtet sein.
Der Installer verändert keine Host- oder Containerkonfiguration. Einen stabilen
Pfad wie `/dev/input/by-id/...-event-kbd` statt einer wechselnden `eventN`-Nummer wählen.
Ob ein Container ohne Gerät startet und Hotplug unterstützt, hängt von dessen
Gerätefreigabe ab. Der Empfangsdienst selbst wartet auf fehlende Geräte.

## Shell und Weboberfläche

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

Das Shell-Setup bleibt vollständig nutzbar und fragt auch nach Weboberfläche und
Übertragung von Scans. Die GUI ist standardmäßig deaktiviert. Bei Aktivierung ist sie
unter `http://<linux-adresse>:8765` erreichbar. Sie hat **keinen Login**: Nur in einem
vertrauenswürdigen internen Netz betreiben, keine öffentliche Portfreigabe einrichten.
Mit `web-host 127.0.0.1` sind nur Browser direkt auf dem Linux-System zugelassen.
Dadurch geht der Zugriff von einem anderen Rechner verloren; die Rückkehr erfolgt
per Shell mit `myscanner set web-host 0.0.0.0`. Die GUI warnt vor Änderungen, die
den Webzugriff unterbrechen können. `myscanner set gui false`
schaltet nur die Oberfläche ab; Scanner und MQTT arbeiten weiter.

Die Oberfläche bietet Einrichtung, Scanner-/MQTT-Verbindungsstatus, Warteschlangengröße,
Zeitpunkt des letzten Scans, lokalen Scannertest und einen Layoutvergleich.
Leere Passwortfelder erhalten das gespeicherte MQTT-Passwort. Shell und GUI verwenden
dieselbe validierte Konfiguration. Speichern lädt den Empfangsdienst neu; während
dieser kurzen Unterbrechung nicht scannen. Bei geändertem Webport oder Bind-Adresse
die neue Adresse aufrufen.

### In Ruhe testen

`myscanner set send false` oder der GUI-Schalter deaktiviert den **Scanversand**
dauerhaft, auch über einen Neustart hinweg. Neue Testscans werden verworfen und
nicht später nachgesendet. Bereits wartende echte Scans bleiben erhalten und
pausieren. Eine bereits an MQTT übergebene Nachricht kann noch ankommen. Discovery
und Verfügbarkeit werden weiterhin gesendet. Mit `myscanner set send true` den
normalen Versand ausdrücklich wieder einschalten.

Der gemeinsame Bereich **Test & Kalibrierung** pausiert beim Start automatisch nur
die Übertragung von Scans. MQTT und Discovery bleiben verbunden. Der erste Scan,
Abbruch oder spätestens zwei Minuten beenden die Pause und stellen den vorherigen
Übertragungszustand wieder her. Eine dauerhaft ausgeschaltete Übertragung bleibt aus.
Eine bereits vor dem Test an MQTT übergebene Nachricht kann noch ankommen.
Testscans werden nicht in die Outbox eingereiht; wartende echte Scans bleiben erhalten.
Testergebnisse liegen nur im Speicher und werden bis zum Ende der ursprünglichen
Zwei-Minuten-Frist angezeigt. „Test beenden“ entfernt sie sofort.

`myscanner test` bleibt ein eigenständiger Shell-Test: Er stoppt einen aktiven
Empfänger vorübergehend, druckt Scans lokal ohne MQTT und startet den zuvor aktiven
Dienst nach Strg+C wieder. Dabei ist auch die GUI vorübergehend nicht erreichbar.

### Kalibrierung

Text eingeben und lokal im Browser einen QR-Testcode erzeugen. „QR erstellen &
Test starten“ startet zusätzlich die Aufnahme. Ein vorhandener Barcode lässt sich
mit „Nur Scannertest starten“ prüfen; für 1D-Scanner ist kein QR-Code geeignet.
Der Testtext kann bis zu 1000 Zeichen enthalten; sehr große UTF-8-Texte überschreiten
die QR-Kapazität und werden mit einer Meldung abgelehnt.

Die Oberfläche vergleicht US-/DE-Interpretationen mit dem Solltext. Das Testlayout
kann ohne erneuten Scan umgeschaltet werden. Erst „Layout speichern“ übernimmt es
für den normalen Empfang. Die Tastaturansicht hebt erkannte physische Tastencodes
hervor, einschließlich Shift/AltGr; ihre Beschriftung folgt dem gewählten Layout.
Y/Z und Sonderzeichen unterscheiden Layouts; reine Ziffern oft nicht.
Die Scannerhardware wird nicht umprogrammiert. Bereits im Scanner verlorene Zeichen
können nicht rekonstruiert werden. Freie Tastenzuordnungen und weitere Layouts sind
noch nicht enthalten.

Die Geräteauswahl bietet erkannte Geräte und eine freie Pfadeingabe. Ein Button
kann aus der Scannerkennung das Standard-Topic erzeugen. Führende/abschließende
Slashes verändern ein MQTT-Topic und werden vom Generator nicht ergänzt.

## Weitere Einstellungen

```bash
myscanner set host broker.example.net
myscanner set user scanner
myscanner set password
myscanner set layout de
myscanner set name Scanner
myscanner set tls true
myscanner set port 8883
myscanner set ca-file /etc/usb-scanner-mqtt/broker-ca.pem
```

`set password` fragt verdeckt ab, kein Passwort als Argument angeben. `ip` und `pw`
sind Aliase für `host` und `password`. Die CA-Datei ist nur bei eigener CA nötig.
TLS prüft das Brokerzertifikat. Änderungen starten einen laufenden Dienst neu.

## Home Assistant und MQTT

In Home Assistant die MQTT-Integration mit demselben Broker verbinden. Discovery
erzeugt ein Gerät mit dem konfigurierten Namen und einen Sensor **Last scan**.
Der Zustand enthält den Barcode, die Attribute `barcode`, `scanner`, `scan_id` und
`timestamp`. Über 255 Zeichen lautet der Zustand `QR scan`, der vollständige Text
bleibt im Attribut. Maximal 4096 Zeichen pro Scan.

Standard-Topic: `usb-scanner-mqtt/usb-scanner-1/scan`

```json
{"ean":"0012345678905","scanner":"usb-scanner-1","scan_id":"unique-scan-id","timestamp":"2026-01-01T12:00:00+00:00"}
```

`ean` ist immer ein String, auch bei QR-Text. Jeder abgeschlossene neue Scan bekommt
eine neue ID, auch bei gleichem Inhalt. Wiederholungen einer wartenden Nachricht
behalten ID und ursprüngliches Topic. MQTT 5, QoS 1, **Scans ohne Retain**.
Empfänger müssen über Scannerkennung und Scan-ID deduplizieren; eine Broker-Bestätigung
bestätigt keine Verarbeitung in Home Assistant.

Discovery und Verfügbarkeit sind retained. HA-Birth auf `<discovery_prefix>/status`
(Standard `homeassistant/status`) veröffentlicht Discovery erneut, ohne alte Scans
zu wiederholen. MQTT-Berechtigungen müssen diese Veröffentlichungen und das
Abonnement erlauben. Verfügbar ist der Scanner bei geöffnetem Gerät und verbundenem Broker.

Für HA List Manager einen JSON-MQTT-Scanner mit Barcode-Feld `ean`, Scannerkennungsfeld
`scanner` und Scan-ID-Feld `scan_id` konfigurieren. Dieselben Nachrichten nur über
eine Scannerquelle verarbeiten.

## Betrieb und Speicherung

Bis zu 1000 Scans werden bei MQTT-Ausfällen in einer persistenten FIFO gespeichert.
Bei voller Queue wird ein Fehler gemeldet, vorhandene Scans werden nicht verdrängt.
Die Queue schützt vor MQTT-Ausfällen; Home Assistant kann unretained Nachrichten
verpassen, wenn es selbst offline ist.

- `/etc/usb-scanner-mqtt/config.json`: Einstellungen und Zugangsdaten, Modus 0600.
- `/var/lib/usb-scanner-mqtt/outbox.sqlite3`: wartende Scans, Modus 0600.
- `/opt/usb-scanner-mqtt/`: aktuelle/vorherige Programmrevision und Python-Umgebung.

Der Dienst läuft für Gerätezugriff als root mit systemd-Beschränkungen. Die optionale
GUI erlaubt Konfigurationsänderungen; nur Konfigurations- und Zustandsverzeichnisse
sind beschreibbar. Normalerweise werden weder Scaninhalte noch Passwörter geloggt.
MQTT, Outbox und ausdrücklich gestartete Tests enthalten echte Scaninhalte.
Scaninhalte werden niemals als Befehle ausgeführt oder als URLs geöffnet.

US/DE mit Shift, Caps und häufigen AltGr-Zeichen werden unterstützt. Enter,
Nummernblock-Enter und Tab schließen Scans ab. Unbekannte Sequenzen verwerfen den
Scan; Teilscans verfallen nach zwei Sekunden. Mehrere Scanner pro Dienst und
automatisches Aufräumen alter Discovery-Einträge sind noch nicht umgesetzt.

## Entwicklung und Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
bash -n install.sh
PYTHONPATH=src python3 tests/mqtt_smoke.py
```

Der optionale MQTT-Test braucht Paho und ein lokales Mosquitto (`MOSQUITTO_BINARY`
kann den Pfad setzen). Der Installer installiert keinen Broker. Installer-Tests
verwenden nachgebildete apt-/systemd-Befehle und ersetzen keinen Linux-Installationstest.
HTTP-Tests verwenden einen lokalen Testserver; sie ersetzen keinen Hardwaretest.

Die lokal mitgelieferte QR-Bibliothek von Project Nayuki steht unter der MIT-Lizenz;
Quelle und Lizenz siehe [Drittanbieterhinweise](THIRD_PARTY_NOTICES.md).
