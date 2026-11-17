# USB 2 MQTT Scanner

[English](README.md)

Scanne einen Barcode oder QR-Code und empfange den Inhalt in Home Assistant.
**Unterstützt werden ausschließlich Barcode- und QR-Scanner, die Linux als
USB-Tastatur erkennt (USB-HID-Tastaturmodus).** Der Scanner überträgt den
gescannten Text dabei wie Tastatureingaben.

Ein mit diesem Projekt getestetes Beispiel: [USB-Barcode-/QR-Scanner bei Amazon
Deutschland (ASIN B08B5MHK3C)](https://www.amazon.de/dp/B08B5MHK3C?th=1).

Der Scanner wird an einen Linux-Rechner angeschlossen. Bei der Installation wählst du:
Einrichtung im Browser (empfohlen) oder mit dem Assistenten im Terminal.

- [Installieren und einrichten](#1-installieren-und-einrichten)
- [Im Browser bedienen](#2-im-browser-bedienen)
- [In Home Assistant verwenden](#3-in-home-assistant-verwenden)
- [Updates und Hilfe](#updates-und-hilfe)
- [Später etwas per Shell ändern](#später-etwas-per-shell-ändern)
- [Technischer Hintergrund](docs/TECHNICAL_de.md)

## 1. Installieren und einrichten

### Das brauchst du

- Einen USB-Barcode- oder QR-Scanner, der wie eine Tastatur arbeitet.
- Einen Linux-Rechner mit Debian 12 oder neuer bzw. Ubuntu 24.04 oder neuer.
  Raspberry Pi OS auf Basis von Debian 12 (Bookworm) oder neuer sollte ebenfalls
  funktionieren, wurde aber **noch nicht auf echter Raspberry-Pi-Hardware getestet**.
  Die folgenden Installationsschritte gelten auch dort.
  Das Programm ist kein Home-Assistant-Add-on und wird nicht direkt auf Home Assistant OS installiert.
- Einen bereits eingerichteten MQTT-Broker: Halte dessen Adresse und gegebenenfalls
  Benutzername und Passwort bereit. Home Assistant muss mit diesem Broker verbunden sein.

Schließe den Scanner an den Linux-Rechner an. Bei einer virtuellen Maschine oder
in einem Container muss der Scanner zuerst dort verfügbar gemacht werden. Für
Proxmox findest du hier [Beispiele für LXC und VM](docs/PROXMOX_de.md).

### Installation starten

Öffne das Terminal **auf dem Linux-Rechner, an dem der Scanner angeschlossen ist**.
Wenn du noch nicht als `root` angemeldet bist, wechsle zuerst mit diesem Befehl:

```bash
sudo -i
```

Kopiere dann diesen Installationsbefehl ins Terminal und drücke Enter:

```bash
wget -qO- https://raw.githubusercontent.com/Nisbo/usb-scanner-mqtt/main/install.sh | bash
```

**Zuerst wählst du die Sprache für die Installation:**

```text
1. English (default)
2. Deutsch
Language / Sprache [1]:
```

**Enter wählt Englisch, 2 wählt Deutsch.** Anschließend erscheinen die Menüs,
Fragen und Hinweise in dieser Sprache. Ohne interaktives Terminal wird Englisch
verwendet. Die Wahl gilt für diesen Aufruf; die Weboberfläche verwendet weiterhin
ihre eigene Browser-Spracherkennung und Sprachauswahl.

**Danach fragt die Installation, wie du einrichten möchtest** (hier Deutsch):

```text
1. Browser (empfohlen)
2. Terminal
Auswahl [1]:
```

**Mit Enter wählst du den Browser.** Es folgen keine Scanner- oder MQTT-Fragen im
Terminal. Nach der Installation werden die erkannten IPv4-Adressen angezeigt,
beispielsweise:

```text
http://192.168.1.50:8765
```

Öffne einen der angezeigten Links im Browser auf deinem PC oder Smartphone.

Wähle im Browser deinen Scanner aus und trage die MQTT-Verbindung ein. Klicke
anschließend auf **Speichern und anwenden**. Danach prüfst du die Zeichen mit der Kalibrierung und kontrollierst einen ersten Scan in Home Assistant, wie unten beschrieben.

Wenn du lieber im Terminal einrichtest, wähle **2**. Der
[Terminal-Assistent ist unten einzeln erklärt](#der-terminal-assistent).
Bei Installation ohne interaktives Terminal wird automatisch der Browser vorbereitet.

Am Ende ist der Dienst eingerichtet. Er läuft nach dem Schließen des Terminals
weiter und startet nach einem Neustart des Linux-Rechners wieder.

## 2. Im Browser bedienen

Verwende zuerst den Link, den die Installation anzeigt. Du kannst ihn im Terminal
auch später mit `myscanner web` erneut anzeigen lassen. Die Adresse hat diese Form:

```text
http://DEINE-LINUX-IP:8765
```

Am einfachsten kopierst du den vollständigen Link aus `myscanner web`. Wenn du
den Web-Port geändert hast, zeigt dieser Befehl auch den passenden Port an.

### Erste Einrichtung im Browser

Der Tab **Einstellungen** öffnet sich automatisch. Er ist in **Scanner**, **MQTT & Home Assistant**, **Verlauf & Produktdaten**, **Weboberfläche** und **Zugangsschutz** unterteilt. Der Button **Speichern und anwenden** speichert alle normalen Einstellungen gemeinsam; Zugangsschutz wird separat gespeichert:

1. Wähle unter **Scanner → Erkannte Geräte** deinen Scanner. Der Gerätename muss nicht dem Namen auf der Verpackung entsprechen. Bei Unsicherheit vergleiche die Liste vor und nach dem Anstecken und klicke auf **Neu suchen**. Wähle keine normale Tastatur.
2. Vergib einen **Anzeigenamen**. Umlaute und Leerzeichen sind erlaubt, etwa `Küche`.
   Die technische **Kennung** kannst du zunächst unverändert lassen.
3. Trage unter **MQTT & Home Assistant** die Brokeradresse ein: **nur IP-Adresse oder
   Hostname**, ohne `http://`, `https://`, `mqtt://` und ohne angehängten Port.
4. Trage den Port und gegebenenfalls MQTT-Benutzer und MQTT-Passwort ein.
   **TLS** nur einschalten, wenn dein Broker einen TLS-Zugang anbietet; häufig ist
   das Port `8883`. Eine übliche Verbindung ohne TLS verwendet Port `1883`.
5. Lass **Gespeichertes Layout**, **Scanner-Ausgabeprofil** und **Scan-Topic** zum
   Start auf ihren Vorschlägen. Die Zeichen prüfst du direkt danach per Kalibrierung.
6. Klicke auf **Speichern und anwenden** und warte kurz. Scanner und MQTT starten jetzt.

### Zuerst die Zeichen prüfen

1. Öffne **Test & Kalibrierung**.
2. Wähle die Sprache der Texte, die du scannen möchtest.
3. Klicke auf **Kalibrierung starten** und scanne den angezeigten QR-Code.
4. Wenn alle Zeichen übereinstimmen, klicke auf **Erkannte Einstellungen übernehmen**.

Damit werden die passenden Empfangseinstellungen gespeichert. Du musst vorher
kein Tastaturlayout oder Ausgabeprofil verstehen. Während dieses Tests werden die
Testscans nicht an Home Assistant weitergegeben.

Bei einem Scanner, der nur Strichcodes lesen kann, trage unter **Eigener Testtext
und weitere Optionen** den bekannten Inhalt eines vorhandenen Barcodes ein. Klicke
auf **Vorhandenen Barcode testen** und scanne deinen vorhandenen Barcode. Dabei wird kein QR-Code benötigt.
Reine Ziffern reichen nicht immer aus, um ein Layout eindeutig zu erkennen.

### Beliebige Codes ansehen und kopieren

Öffne **Scannen**, klicke auf **Scannen starten** und scanne deine Codes nacheinander.
Mit **Produktdaten bei diesen lokalen Scans abfragen** kannst du zusätzlich Produkte nachschlagen, auch wenn die automatische Abfrage ausgeschaltet ist. Diese Auswahl wird in deinem Browser gespeichert und gilt beim nächsten Start des lokalen Scannens. Sie verändert weder den Automatik-Schalter noch den MQTT-Versand.

Jeder Eintrag hat einen **Kopieren**-Button. Löschen und **Liste leeren** verlangen
eine Bestätigung im Dialog. Mit **Beenden** kehrst du zum normalen
Versand an Home Assistant zurück.

Während des lokalen Scannens wird die Weitergabe an Home Assistant pausiert. Nach zwei
Minuten ohne neuen abgeschlossenen Scan endet die Pause automatisch.

Der **dauerhafte Verlauf** zeigt außerdem deine normalen Scans. Jeder Eintrag ist
als **Lokal**, **MQTT – ausstehend**, **MQTT – vom Broker bestätigt** oder
**Übertragung ausgeschaltet** gekennzeichnet. Die Brokerbestätigung sagt noch nicht,
ob Home Assistant den Scan verarbeitet hat. Kalibrierungsscans erscheinen hier nicht.

Standardmäßig bleiben die letzten **1.000 Scans** erhalten, auch nach Updates und
Neustarts. Unter **Einstellungen → Verlauf & Produktdaten** kannst du das Limit ändern.
Mit **Ältere Einträge** blätterst du durch den Verlauf. Einzelne Einträge oder die
Liste kannst du ausdrücklich löschen; wartende MQTT-Nachrichten bleiben dabei erhalten.

### Produktdaten optional ergänzen

Unter **Einstellungen → Verlauf & Produktdaten**:

1. **Produktdaten bei Open Facts abfragen** einschalten.
2. Eine eigene **Sprache der Produktdaten** wählen, unabhängig von der Oberflächensprache.
3. Auf Wunsch **Produktdaten auch an MQTT senden** einschalten.
4. Die Wartezeit bei **2 Sekunden** lassen und **Speichern und anwenden** anklicken.

**Nur bei ausdrücklichem Bedarf einschalten:** Bei Verwendung mit HA List Manager übernimmt dieser die Produktabfrage. Zusätzliche Abfragen hier können doppelte Anfragen und Abfragelimits verursachen.

Die Wartezeit ist die maximale Zeit für eine einzelne Produktantwort, nicht eine Pause zwischen Scans. Nach Ablauf wird ohne Produktdaten fortgefahren.

Die Abfrage ist zunächst ausgeschaltet. Wenn du sie einschaltest, werden Zahlencodes
an Open Food Facts gesendet; beliebige QR-Texte und URLs werden nicht abgefragt.
Auch Non-Food-Produkte können gefunden werden. Name, Marke, Packungsgröße und
Produkttyp erscheinen beim Scan; ein vorhandenes Produktbild kannst du im Dialog groß ansehen. Das Bild wird erst
beim Öffnen geladen; **Schließen** oder **Escape** schließt die Ansicht.

Bei aktivierter MQTT-Ergänzung enthält **dieselbe Scan-Nachricht** zusätzlich
`off_status` und `off_data`. Bei Fehlern, ohne Treffer oder nach Ablauf der Wartezeit
wird der Scan trotzdem gesendet, mit `off_data: null`. Es folgt keine zweite Nachricht
nur für Produktdaten. Weitere Scans können während der Abfrage eingelesen werden;
bei vielen Scans kann sich die Versandwarteschlange kurz aufbauen.

Gefundene Produkte werden für **24 Stunden**, fehlende für **eine Stunde** gespeichert,
jeweils pro Produktsprache. Bis zu **15 externe Abfragen innerhalb der jeweils
letzten 60 Sekunden** sind möglich, auch direkt hintereinander. Cachetreffer zählen
nicht mit. Erst wenn das Budget verbraucht ist oder ein Fehler auftritt, wird
pausiert. Der Eintrag nennt den damaligen Grund; Scans werden trotzdem übertragen. Mit **Produktcache
leeren** erzwingst du nach Ablauf einer eventuellen Abfragepause neue Abfragen.
Verlauf und Cache bleiben bei Updates und Deinstallation mit Datenerhalt erhalten.

Quelle der Produktdaten: [Open Food Facts](https://world.openfoodfacts.org), Daten
unter [ODbL](https://opendatacommons.org/licenses/odbl/1-0/); für verlinkte Bilder gelten
[die Bedingungen von Open Food Facts](https://world.openfoodfacts.org/terms-of-use).

### Einstellungen ändern

Unter **Einstellungen** kannst du Scanner, MQTT-Verbindung und Gerätenamen ändern.
Klicke anschließend auf **Speichern und anwenden**. Warte kurz, bevor du wieder scannst.
Ein leeres Feld für das neue MQTT-Passwort erhält das bisherige Passwort.

Unter **Status** siehst du, ob Scanner und MQTT verbunden sind. Dort kannst du die
Weitergabe von Scans auch dauerhaft aus- oder wieder einschalten.

### Passwort, Sprache und Farben

- **Passwortschutz:** Unter **Einstellungen → Zugangsschutz** aktivieren, ein eigenes
  Passwort mit mindestens acht Zeichen zweimal eingeben und separat speichern.
  Dort kannst du es auch ändern oder den Schutz wieder ausschalten.
- **Automatisch abmelden:** Auf Wunsch im selben Bereich aktivieren. Die Option ist zunächst aus.
- **Sprache:** Oben rechts Deutsch oder Englisch auswählen. Zunächst wird die
  Browsersprache verwendet; deine Auswahl wird in diesem Browser gespeichert.
- **Hell/Dunkel:** Mit Sonne/Mond oben rechts umschalten. Auch diese Wahl bleibt im Browser gespeichert.

Die Weboberfläche hat zunächst keinen Passwortschutz. Das Web-Passwort ist unabhängig
vom MQTT-Passwort und wird für Shell-Befehle nicht benötigt. Verwende die Oberfläche
im eigenen vertrauenswürdigen Netz; der eingebaute HTTP-Zugriff ist nicht verschlüsselt.

## 3. In Home Assistant verwenden

1. Stelle sicher, dass die MQTT-Integration in Home Assistant mit demselben Broker verbunden ist.
2. Öffne **Einstellungen → Geräte & Dienste → MQTT** und suche nach dem
   Anzeigenamen, den du bei der Einrichtung vergeben hast.
3. Dort erscheint der Sensor **Last scan** für den zuletzt gescannten Inhalt.
4. Beende eine eventuell laufende lokale Aufnahme im Tab **Scannen** und scanne
   einen normalen Barcode. Prüfe, ob er in Home Assistant ankommt.

Auch QR-Texte können übertragen werden. Lange Texte findest du im Sensorattribut
`barcode`. Jeder neue Scan erhält eine neue Scan-ID, auch wenn du denselben Code mehrfach scannst.

Für Automationen oder andere Anwendungen findest du das Nachrichtenformat unter
[Technischer Hintergrund](docs/TECHNICAL_de.md#mqtt-und-home-assistant).

### Direkt in Home Assistant steuern

Beim Scanner-Gerät erscheinen automatisch drei Schalter:

| Schalter in HA | Funktion |
| --- | --- |
| **Scan forwarding** | Dauerhafte Weitergabe von Scans an MQTT ein-/ausschalten. |
| **Product lookup** | Open-Facts-Abfragen ein-/ausschalten. |
| **Include product data** | Produktdaten in derselben MQTT-Nachricht mitsenden oder nur im Verlauf anzeigen. |

Die Änderungen werden gespeichert und gelten auch nach einem Neustart. Die GUI
zeigt Änderungen aus HA automatisch an; noch nicht gespeicherte Formulareingaben
werden dabei nicht überschrieben. Änderungen in der GUI erscheinen nach dem
Speichern auch in HA. Eine lokale Aufnahme oder Kalibrierung pausiert den Versand
weiterhin, auch wenn **Scan forwarding** eingeschaltet ist.

Nach Updates, HA-Neustarts und erneuter MQTT-Verbindung werden Geräteerkennung
und Zustände erneut gesendet. Eine Neuinstallation ist dafür nicht nötig. Die
Schalter bleiben bei abgezogenem Scanner bedienbar; der Scan-Sensor ist dann
nicht verfügbar.

### Produkt in HA manuell nachschlagen

Beim selben Scanner-Gerät erscheinen zusätzlich:

- **Product query: EAN** – Zahlencode eingeben und übernehmen. Führende Nullen bleiben erhalten.
- **Product query: Start lookup** – die eingetragene EAN abfragen.
- **Product query: Result** – Produktname oder verständlicher Abfragestatus.

Das Eingabefeld allein startet noch keine Abfrage. Der Button funktioniert auch
mehrfach mit derselben EAN und auch dann, wenn **Product lookup** oder **Scan forwarding**
ausgeschaltet ist. Die manuelle Abfrage ist ein bewusster, separater Aufruf; Cache,
Produktsprache, Wartezeit und Abfragelimits sind dieselben wie beim Scanner.

Das Ergebnis gehört **nicht zum Scan-Topic** und erzeugt keinen Eintrag im
Scanverlauf. Andere Integrationen, die auf Scans warten, erhalten dadurch keinen
vermeintlichen Scan. Eingabe und letztes Ergebnis bleiben nach einem Neustart erhalten.
Der Ergebnis-Sensor enthält als Attribute unter anderem die tatsächlich abgefragte
`ean`, `status`, `language`, `cached` und `off_data` mit Name, Marke, Packungsgröße
und Bildadresse. Eine neue Eingabe verändert das bisherige Ergebnis erst nach
**Start lookup**. Bei sehr schnellen Buttonklicks zählt die neueste wartende Abfrage.

**Optional: zusammen auf dem Dashboard.** Eine Entitätenkarte mit eigenem Rahmen
kann so aussehen (für die Standard-Kennung `usb-scanner-1`; bei anderer Kennung
die drei Entity-IDs durch deine tatsächlichen Entity-IDs ersetzen):

Öffne dein HA-Dashboard → **Dashboard bearbeiten → Karte hinzufügen → Manuell** und füge den folgenden Text ein. Die tatsächlichen Entity-IDs findest du unter dem Scanner-Gerät, indem du die jeweilige Entität und ihre Einstellungen öffnest. Sie können nach Umbenennungen oder Namenskonflikten vom Beispiel abweichen.

```yaml
type: entities
title: Produktabfrage
entities:
  - entity: text.usb_scanner_mqtt_usb_scanner_1_lookup_ean
    name: EAN
  - entity: button.usb_scanner_mqtt_usb_scanner_1_lookup_start
    name: Produkt abfragen
  - entity: sensor.usb_scanner_mqtt_usb_scanner_1_lookup_result
    name: Ergebnis
  - type: attribute
    entity: sensor.usb_scanner_mqtt_usb_scanner_1_lookup_result
    attribute: ean
    name: Abgefragte EAN
```

### Scanner-ID behalten – auch auf einem neuen Rechner

Die **Kennung** bestimmt die feste HA-Zuordnung, unabhängig vom Anzeigenamen und
von der Installation. Für `kueche` wird als Entitäts-ID
`sensor.usb_scanner_mqtt_kueche_last_scan` vorgeschlagen. Auf einem Ersatzrechner
wieder dieselbe Kennung und denselben MQTT-Broker verwenden. Den Anzeigenamen
kannst du jederzeit ändern. Zwei gleichzeitig verwendete Scanner brauchen
unterschiedliche Kennungen.

## Updates und Hilfe

### Aktualisieren

Diesen Befehl im Terminal des Linux-Rechners als `root` ausführen:

```bash
myscanner update
```

Danach die Browserseite mit **Strg+F5** neu laden. Deine Einstellungen und wartenden
MQTT-Scans bleiben erhalten. Updates erfolgen nur auf deinen Aufruf hin.

### Installationsbefehl erneut ausführen

Wenn bereits eine Installation oder gespeicherte Einstellungen vorhanden sind,
zeigt der Installationsbefehl dieses Menü:

| Auswahl | Was passiert? |
| --- | --- |
| **1 – Aktualisieren / reparieren** (Enter) | Installiert den aktuellen GitHub-Stand und ergänzt fehlende Pakete. Einstellungen, Passwörter und wartende Scans bleiben erhalten. |
| **2 – Einrichtung zurücksetzen und neu beginnen** | Löscht Einstellungen, Passwörter und wartende Scans nach Bestätigung mit `DELETE`. Danach wählst du erneut Browser oder Terminal und richtest den Scanner neu ein. |
| **3 – Deinstallieren** | Öffnet die unten beschriebene Auswahl: Daten behalten oder vollständig löschen. |
| **0 – Beenden** | Bricht ab, ohne die Installation zu verändern. |

**Zum Testen einer vollständigen Neueinrichtung wähle 2.** Die bisherigen Daten
werden dabei gelöscht. Die USB-Freigabe in Proxmox bleibt erhalten.

Bei Auswahl 1 und 2 wird der Dienst neu gestartet; danach meldest du dich im Browser
erneut an. Auswahl 1 behält den Verlauf und Produktcache, Auswahl 2 löscht sie. `myscanner update` aktualisiert
weiterhin direkt ohne dieses Menü. Ohne interaktives Terminal behält der Installer
die vorhandenen Einstellungen und aktualisiert ohne Rückfragen.

### Deinstallieren

Im Terminal als `root` ausführen:

```bash
myscanner uninstall
```

Wähle **1**, um nur das Programm zu entfernen und Einstellungen samt wartenden
Scans für eine spätere Neuinstallation zu behalten. **2** entfernt auch diese Daten
und die gespeicherten Passwörter. **0** bricht ab.

Die Entfernung muss bestätigt werden: bei Datenerhalt mit `yes` (Englisch) bzw.
`ja` (Deutsch), beim vollständigen
Löschen mit `DELETE`. Das Programm stoppt zuerst seinen Dienst. Gemeinsam verwendete
Systempakete und Proxmox-Gerätefreigaben bleiben bestehen. Das alte MQTT-Gerät in
Home Assistant kannst du bei Bedarf dort manuell löschen.

### Die Weboberfläche wurde nicht eingeschaltet?

Im Terminal als `root` ausführen, danach die Browseradresse von oben öffnen:

```bash
myscanner set gui true
```

### Web-Passwort vergessen?

Im Terminal als `root` ausführen:

```bash
myscanner reset-login
```

Das entfernt nur den Web-Passwortschutz. Scanner- und MQTT-Einstellungen bleiben erhalten.

### Etwas funktioniert nicht?

| Problem | Erster Schritt |
| --- | --- |
| Keine Weboberfläche erreichbar | IP-Adresse und Web-Port prüfen. Die Weboberfläche gegebenenfalls mit dem Befehl oben einschalten. |
| Scanner piept, aber kein Scan erscheint | Der Scanner muss jeden Scan mit Enter oder Tab abschließen. Diese Einstellung steht im Scannerhandbuch. Bei falschen Zeichen zusätzlich kalibrieren. |
| Scanner nicht verbunden | USB-Verbindung prüfen; bei VM/Container auch die Gerätefreigabe. Unter Einrichtung das richtige Gerät auswählen. |
| MQTT nicht verbunden | Unter Einrichtung Adresse, Port und Zugangsdaten des Brokers prüfen. |
| Falsche Zeichen | Die geführte Kalibrierung im Browser durchführen. |
| In Home Assistant kommt nichts an | Lokale Aufnahme beenden und unter Status die Übertragung einschalten. Verbindung beider Programme zum selben MQTT-Broker prüfen. |

Weitere Hinweise liefert im Terminal:

```bash
myscanner status
```

Wenn du Hilfe suchst, sind außerdem die Meldungen aus `myscanner logs` nützlich.
Die Anzeige beendest du mit **Strg+C**. Teile keine Passwörter oder privaten Scaninhalte.

## Später etwas per Shell ändern

**Optional:** Nutze diesen Abschnitt, wenn du lieber im Terminal arbeitest.
Für dieselben Änderungen im Browser reicht der Tab **Einstellungen**.
Alle folgenden Befehle werden auf dem Linux-Rechner als `root` ausgeführt.

Die Auswahl Browser/Terminal erneut öffnen:

```bash
myscanner setup
```

Oder den Terminal-Assistenten direkt starten:

```bash
myscanner setup --mode shell
```

### Der Terminal-Assistent

Die Fragen erscheinen in der am Anfang gewählten Sprache. Die Tabelle zeigt die
englischen Bezeichnungen. Ein Wert in eckigen Klammern ist der Vorschlag;
**Enter behält ihn bei**. Bei vorhandener Einrichtung werden deine gespeicherten
Werte vorgeschlagen. Bei einer neuen Einrichtung gelten die unten genannten Startwerte.

| Frage | Bedeutung und Eingabe |
| --- | --- |
| `Scanner device: path or number` | Oberhalb der Frage stehen gefundene Eingabegeräte mit Nummer, Gerätename und Pfad. Gib die Nummer deines Scanners ein. Bei nur einem Gerät wird dessen Pfad vorbelegt. Ohne Treffer erscheint ein Hinweis; dann USB/Freigabe prüfen. |
| `Scanner ID` | Feste Kennung für MQTT und HA; auf einem Ersatzrechner dieselbe Kennung wiederverwenden. Vorschlag `usb-scanner-1`; erlaubt sind Buchstaben ohne Umlaute, Ziffern, Bindestrich und Unterstrich. |
| `Name shown in Home Assistant` | Frei wählbarer Anzeigename. Auch `Küche` und Leerzeichen funktionieren. |
| `Layout configured ON the scanner` | Startwert `us`, nicht automatisch erkannt. Bei Unkenntnis Enter drücken und anschließend im Browser kalibrieren. |
| `Output profile` | Legt fest, wie zusätzliche Zeichen gelesen werden. Startwert `standard`, nicht automatisch erkannt. Bei Unkenntnis Enter drücken; die Kalibrierung prüft das Profil mit. |
| `MQTT scan topic` | Adresse für Scanmeldungen. Wird aus der Kennung vorgeschlagen, etwa `usb-scanner-mqtt/usb-scanner-1/scan`. Meist Enter drücken. |
| `MQTT broker IP or hostname` | Nur Adresse oder Hostname des Brokers, ohne `http://`, `https://`, `mqtt://` und ohne Port. |
| `Use TLS?` | `yes` nur bei einem TLS-Zugang deines Brokers. Sonst den Vorschlag `no` übernehmen. |
| `MQTT port` | Häufig `1883` ohne TLS oder `8883` mit TLS. Verwende den tatsächlich am Broker eingerichteten Port. |
| `MQTT username` | Benutzername des vorhandenen Brokers. Verlangt er keine Anmeldung, `-` eingeben. |
| `MQTT password` | Wird bei einem Benutzernamen abgefragt. Die Eingabe ist unsichtbar; das ist normal. |
| `Custom CA certificate path` | Nur bei TLS: Für öffentlich vertrauenswürdige Zertifikate bei neuer Einrichtung leer lassen; einen gespeicherten CA-Pfad mit `-` entfernen. Sonst den Pfad zur eigenen CA-Datei eintragen. |
| `Enable internal web interface?` | Bei neuer Einrichtung ist **`yes` vorausgewählt**. Enter lässt dich später bequem im Browser weiterarbeiten; mit `no` bleibt die Oberfläche aus. |
| `Web bind address` | `0.0.0.0` für Zugriff aus deinem Heimnetz übernehmen. `127.0.0.1` wäre nur direkt auf dem Linux-Rechner erreichbar. |
| `Web port` | Normalerweise den Vorschlag `8765` übernehmen. |
| `Send scans over MQTT?` | **`yes`** für normalen Versand an Home Assistant. |

Nach dem Speichern startet der Empfang. Bei aktivierter Weboberfläche zeigt die
Installation die Browseradressen an; später findest du sie mit `myscanner web`.

Einzelne Einstellungen ändern – **Beispiele ersetzen, nicht die ganze Liste ausführen**:

| Zweck | Befehl |
| --- | --- |
| Brokeradresse ändern | `myscanner set host DEIN-BROKER` |
| MQTT-Benutzer ändern | `myscanner set user DEIN-BENUTZER` |
| MQTT-Passwort ändern | `myscanner set password` – fragt das Passwort verdeckt ab |
| Gerätenamen ändern | `myscanner set name "Mein Scanner"` |
| Weboberfläche einschalten / ausschalten | `myscanner set gui true` / `myscanner set gui false` |
| Scanversand einschalten / ausschalten | `myscanner set send true` / `myscanner set send false` |
| Programm neu starten | `myscanner restart` |

Ein Scan nur im Terminal, ohne Weitergabe an Home Assistant:

```bash
myscanner test
```

Mit **Strg+C** beenden. Während dieses Shell-Tests ist die Weboberfläche vorübergehend
nicht erreichbar. Ein zuvor laufender Empfangsdienst wird anschließend wieder gestartet.

## Hintergrund für Interessierte

Für die Benutzung musst du nicht wissen, welche Python-Pakete installiert werden,
wo die Dateien liegen oder wie MQTT-Nachrichten aufgebaut sind.
Das steht gesammelt im [technischen Hintergrund](docs/TECHNICAL_de.md).

### Zugriff über Nginx und eigene Domains (optional)

Standardmäßig öffnest du die Oberfläche über die IP-Adresse des Linux-Rechners und den Web-Port, z. B. über den Link aus `myscanner web`. Rechnernamen wie `scanner.local` sind nicht automatisch freigegeben.

Für deine Nginx-Domain öffne **Einstellungen → Weboberfläche** über die IP-Adresse. Schalte **Zugriff über eigene Domains erlauben** ein und trage unter **Erlaubte Domains** jeden gewünschten Namen in eine eigene Zeile ein. Beispielnamen durch deine eigenen ersetzen:

```text
domain.de
scanner.domain.de
```

Nur Namen, ohne `http://`, `https://`, Port, Pfad oder `*`. Jeder Name gilt exakt: `domain.de` erlaubt keine Unterdomains. Klicke auf **Speichern und anwenden** und öffne anschließend deine Domain. Nginx verwendet weiterhin deine übliche Zuordnung zur internen IP und zum Web-Port sowie den ursprünglichen Host-Header.

**Achtung:** Fehlt deine Domain oder schaltest du die Freigabe aus, funktioniert der Zugriff über diese Domain nach dem Speichern nicht mehr. Über die IP-Adresse und den Web-Port kannst du die Liste korrigieren. Checkbox aus oder Liste leer erlaubt keine Domains; die IP bleibt möglich. Das schränkt manipulierte Webseiten ein, die deinen Browser für Zugriffe auf lokale Dienste missbrauchen könnten. Die Einstellung des Passwortschutzes bleibt unverändert; CSRF-Prüfungen bleiben aktiv.

**Beim Update von 0.11.0:** Öffne zunächst die IP-Adresse und gib deine Domain ausdrücklich frei. Bisher ohne Freigabe akzeptierte Domainnamen werden nun abgewiesen.
