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

Der Verlauf liegt dauerhaft in SQLite neben der Outbox. Standard: 1.000 Einträge (einstellbar 1–10.000), einschließlich lokaler und normaler Scans sowie ausgeschalteter Übertragung. Kalibrierung wird nicht gespeichert. Löschen des Verlaufs entfernt keine wartenden MQTT-Nachrichten.

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
zeitgesteuertes Sitzungslimit. Normales Speichern erhält Sitzungen beim Neuladen des Empfängers. Ein Programmneustart beendet sie.
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

## Optionale Open-Facts-Ergänzung

GUI: Einrichtung → Verlauf & Produktdaten. Standardmäßig aus; eigene Produktsprache
(en/de/fr/es/it/nl/pt/pl), Wartezeit 2 Sekunden (1–5). Abgefragt werden ausschließlich
ASCII-Zahlencodes mit 4–32 Stellen, führende Nullen bleiben erhalten. API v3 mit
product_type=all berücksichtigt auch Non-Food. Quelle: [offizielle API-Doku](https://openfoodfacts.github.io/openfoodfacts-server/api/) und [universelle Abfrage](https://openfoodfacts.github.io/openfoodfacts-server/api/tutorials/scanning-cosmetics-pet-food-and-other-products/).

Lookup-Aufträge werden mit dem Scan dauerhaft gespeichert. Der Hintergrundarbeiter
ergänzt bei aktivierter MQTT-Option dieselbe Outbox-Nachricht um off_status/off_data,
bevor sie gesendet wird. Scan-ID, Zeit und Topic bleiben unverändert; keine zweite
Ergänzungsnachricht. Ohne MQTT-Option erscheinen Produktdaten nur im Verlauf, ohne
Versandverzögerung. Verlauf löschen oder begrenzen lässt wartende MQTT-Aufträge
bestehen. Ausschalten der Abfrage beendet ältere Aufträge ohne weitere HTTP-Anfrage.

Statuswerte: found, not_found, not_applicable, timeout, error, local_rate_limited, server_rate_limited, cooldown,
unavailable, disabled (rate_limited bleibt für ältere Einträge erhalten); im Verlauf zusätzlich pending. Produktfelder: name, brand,
package_quantity, image_url, product_type, source. HA-Sensorattribute enthalten
ebenfalls off_status/off_data. Ohne Daten ist off_data null.

Cache pro exaktem Code und Produktsprache: Treffer 24h, fehlend 1h, maximal 5.000
Einträge. Fehler gelten nicht als fehlendes Produkt. Gleitendes Fenster mit bis zu 15 HTTP-Abfragen in den jeweils letzten 60 Sekunden,
ohne starren Abstand; Zeitstempelbudget und HTTP-Gate überleben GUI-Reloads. Cachetreffer
umgehen die Begrenzung. Lokales Budgetlimit und tatsächliches HTTP 429 sind getrennt. Bei Störungen
60s Abfragepause. Andere Anwendungen derselben IP können ebenfalls Limits auslösen.
Ein separater HTTP-Daemon-Thread mit begrenzter Antwortgröße (512 KiB) stellt sicher,
dass auch hängende DNS-/HTTP-Aufrufe den Scanner nicht blockieren und keine
unbegrenzten Threads starten. Nach Überschreiten der Wartezeit werden weitere
unbekannte Produkte übersprungen, solange der alte HTTP-Aufruf hängt. Neustart
setzt diesen Zustand zurück. Bei Scanfolgen kann eine Warteschlange entstehen;
die eingestellte Wartezeit gilt pro Abfrage.

Verlauf, Aufträge und Cache liegen in outbox.sqlite3. Updates/Datenerhalt behalten
sie, vollständige Deinstallation/Reset löschen sie. Produkttexte werden als Text
gezeigt; große Bilder werden erst auf Klick im Dialog geladen; Escape/Schließen entfernt die Bildadresse. CSP erlaubt ausschließlich HTTPS-Bilder der vier Open-Facts-Bildhosts. Quellen-/Lizenzhinweise (ODbL)
stehen in GUI und README.

Ausgewählte Bildadressen werden gemäß der [offiziellen Bilddokumentation](https://openfoodfacts.github.io/openfoodfacts-server/api/how-to-download-images/) auf die vollständige Auflösung umgestellt. Alte Cache-/Verlaufseinträge mit Vorschaubildern oder unknown-Mengen werden bei der Anzeige bereinigt; bereits gesendete Nachrichten bleiben unverändert.

## MQTT-Steuerung und feste HA-Identität (0.8.0)

Identität: `usb_scanner_mqtt_<Scanner-ID>`; vorgeschlagene Sensor-Entitäts-ID:
`sensor.usb_scanner_mqtt_<Scanner-ID-mit-Unterstrichen>_last_scan`.
Installations-Zufallskennung und Anzeigename beeinflussen weder Identität,
Discovery-Topics, Client-ID noch Verfügbarkeits-Topics. Es gibt keine Migration und
keine automatische Entfernung alter Discovery-Nachrichten. HA kann manuell
vergebene Entitäts-IDs behalten und bei Namenskollisionen Suffixe ergänzen. Gleiche
Scanner-ID am selben Broker bedeutet dasselbe Gerät und denselben MQTT-Client;
solche Instanzen nicht gleichzeitig betreiben.

Sensor und drei Schalter teilen dieselbe Gerätekennung. Schalter-Schlüssel:
`scan_forwarding`, `open_facts`, `product_data`. Je Schalter:

- Befehl: `usb-scanner-mqtt/<Scanner-ID>/control/<Schlüssel>/set` (ON/OFF, QoS 1, nicht retained).
- Zustand: `usb-scanner-mqtt/<Scanner-ID>/control/<Schlüssel>/state` (ON/OFF, QoS 1, retained).
- Dienst-Verfügbarkeit: `usb-scanner-mqtt/<Scanner-ID>/status/availability`.
- USB-Verfügbarkeit: `usb-scanner-mqtt/<Scanner-ID>/availability`.

Der Sensor benötigt beide Verfügbarkeiten online (`all`), Schalter nur die
Dienst-Verfügbarkeit. Last Will setzt diese bei einem Absturz retained auf offline.
Bei MQTT-Verbindung und HA-Birth werden Discovery, gespeicherte Zustände und
Verfügbarkeit erneut gemeldet. Scans bleiben nicht-retained. Schalter zeigen die
gespeicherte Einstellung, nicht die vorübergehende Pause einer lokalen Aufnahme.

MQTT-5-Subscriptions: retainAsPublished=true, retainHandling=2. Retained und
ungültige Befehle werden ignoriert, auch retained veröffentlichte Live-Befehle.
Der Callback merkt nur den neuesten Wert pro erlaubtem Schlüssel (maximal drei).
Dateizugriffe übernimmt der Outbox-Worker. GUI- und MQTT-Änderungen verwenden die
gleiche Settings-Sperre und erhalten andere Einstellungen. Befehle sind idempotent;
erst nach dem Speichern werden Laufzeit und Zustandsmeldung geändert. Kein
Empfänger-Neuladen und kein Logout nötig. Lookup-Worker wird sofort umgeschaltet;
bereits gestartete HTTP-Anfragen können noch abschließen. Wartende Scans behalten
ihre bei Aufnahme festgelegte Produktdaten-Regel. Keine allgemeinen
Konfigurations- oder Shell-Befehle werden über MQTT angenommen.

Der Broker muss HA-Birth/Befehlstopics zum Abonnieren und Scan-, Discovery-,
Zustands- und Verfügbarkeitstopics zum Veröffentlichen erlauben. Broker-Zugang und
ACL regeln die MQTT-Steuerung; der Web-Passwortschutz ersetzt diese nicht.
Protokollreferenzen: [HA MQTT Switch](https://www.home-assistant.io/integrations/switch.mqtt/),
[HA MQTT Sensor](https://www.home-assistant.io/integrations/sensor.mqtt/).

## Manuelle Produktabfrage aus HA (0.9.0)

Zusätzliche Text-, Button- und Sensor-Discovery auf demselben Gerät; IDs aus der
Scanner-ID, bestehende Sensor-/Schalter-IDs unverändert. Alle drei benötigen nur
Dienst-Verfügbarkeit, kein USB-Gerät. Das Icon von Product lookup ist mdi:barcode-scan.

Eigener Namensraum unter `usb-scanner-mqtt/<Scanner-ID>/lookup/`:

| Suffix | Nutzlast / Verhalten |
| --- | --- |
| `ean/set` | ASCII-Ziffern, 0–32 Stellen; Befehl nicht retained. Leer löscht das Eingabefeld. |
| `ean/state` | Retained JSON `{"ean":"00123"}`; HA-Texttemplate liest ean als Text. JSON-Hülle erlaubt retained leere Eingaben. |
| `start` | Exakt `LOOKUP`, nicht retained; erfasst die beim Buttondruck gewählte EAN. |
| `result` | Retained JSON mit state, status, ean, request_id, timestamp, language, cached, off_data. |

Abfragen brauchen 4–32 Ziffern. Eine Eingabe oder HA-Birth allein startet keine
Abfrage. Retained Live-Befehle und beim Verbinden gespeicherte Befehle werden wie
bei den Schaltern ignoriert. Callback hält nur neuesten Eingabewert und neuesten
Buttonauftrag im RAM; Persistenz/Publikation übernimmt der Outboxworker. Ergebnis
und Eingabe liegen mit höchstens einem wartenden manuellen Job in einer separaten
SQLite-Tabelle manual_lookup. Kein Aufruf von Outbox.put oder History.record.

Der bestehende Enricher nutzt dieselbe Lookup-Instanz und denselben Cache sowie
prozessweiten RequestBudget. Explizite manuelle Jobs funktionieren unabhängig vom
Automatik-Schalter und der Scanübertragung. Bei wartenden Scannerjobs wechseln
manuelle und automatische Jobs sich ab, damit Scans nicht verhungern. Eine neuere
Abfrage ersetzt einen älteren wartenden Auftrag; ein verspätetes Ergebnis einer
älteren request_id darf das neue Ergebnis nicht überschreiben.

Resultatstatus idle/pending/invalid_input sowie die vorhandenen Lookup-Statuswerte.
state ist Produktname (maximal 255 Zeichen) oder verständlicher Status, off_data
bleibt vollständig. Jede angenommene Buttonabfrage bekommt eine eigene request_id,
auch bei identischer EAN und Cachetreffer. Bereits übernommene manuelle Jobs und
letztes Ergebnis überleben den Empfänger-Neustart; Löschen des Scanverlaufs ändert
sie nicht. HA-Neustart/Connect sendet das letzte Ergebnis erneut, ohne neue HTTP-
Abfrage. Ein angefangener HTTP-Aufruf bleibt nicht stornierbar, ein veraltetes
Ergebnis wird jedoch nicht als neuestes übernommen.

Referenzen: [MQTT Text](https://www.home-assistant.io/integrations/text.mqtt/),
[MQTT Button](https://www.home-assistant.io/integrations/button.mqtt/).
