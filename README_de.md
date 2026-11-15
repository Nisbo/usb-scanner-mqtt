# USB 2 MQTT Scanner

[English](README.md)

Scanne einen Barcode oder QR-Code und empfange den Inhalt in Home Assistant.
Der Scanner wird an einen Linux-Rechner angeschlossen. Ein Assistent hilft bei der
Ersteinrichtung; danach kannst du die Einstellungen bequem im Browser ändern.

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
  Das Programm ist kein Home-Assistant-Add-on und wird nicht direkt auf Home Assistant OS installiert.
- Einen bereits eingerichteten MQTT-Broker: Halte dessen Adresse und gegebenenfalls
  Benutzername und Passwort bereit. Home Assistant muss mit diesem Broker verbunden sein.

Schließe den Scanner an den Linux-Rechner an. Bei einer virtuellen Maschine oder
in einem Container muss der Scanner zuerst dort verfügbar gemacht werden.

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

**Die Installation startet anschließend automatisch einen Einrichtungsassistenten.**
Du musst keine Konfigurationsdatei bearbeiten und danach keine weitere Befehlsliste ausführen.

### Die Fragen des Assistenten beantworten

Die Fragen im Terminal sind auf Englisch. Ein Wert in eckigen Klammern ist der
Vorschlag: **Mit Enter übernimmst du ihn.**

| Frage im Assistenten | Was du eingibst |
| --- | --- |
| `Scanner device: path or number` | Die Nummer deines Scanners aus der angezeigten Geräteliste. Wähle keine normale Tastatur. |
| `Scanner ID` | Für einen einzelnen Scanner kannst du den Vorschlag mit Enter übernehmen. |
| `Name shown in Home Assistant` | Den gewünschten Gerätenamen, beispielsweise `Kuechen-Scanner`. |
| `Layout configured ON the scanner`, `Output profile`, `MQTT scan topic` | Zum Start die Vorschläge mit Enter übernehmen. Die Zeichen prüfst du anschließend im Browser mit der Kalibrierung. |
| `MQTT broker IP or hostname` | Die Adresse deines MQTT-Brokers. Das ist kein neu anzulegender Zugang. |
| `Use TLS?`, `MQTT port` | Die Verbindungsdaten deines Brokers. Die Vorschläge passen zu einer üblichen unverschlüsselten Verbindung auf Port 1883. |
| `MQTT username` und gegebenenfalls `MQTT password` | Die Zugangsdaten deines Brokers. Falls dieser keine Anmeldung verlangt, beim Benutzernamen `-` eingeben. Beim Tippen des Passworts sind keine Zeichen sichtbar – das ist normal. |
| `Enable internal web interface?` | **`yes` eingeben**, wenn du anschließend alles Weitere im Browser erledigen möchtest. Für reine Shell-Bedienung `no` wählen. |
| `Web bind address`, `Web port` | Für den Zugriff aus deinem Heimnetz die Vorschläge mit Enter übernehmen. |
| `Send scans over MQTT?` | **`yes`**, damit normale Scans an Home Assistant weitergegeben werden. |

Am Ende startet das Programm automatisch. Es läuft auch dann weiter, wenn du das
Terminal schließt, und startet nach einem Neustart des Linux-Rechners wieder.

Die erste Grundeinrichtung erfolgt derzeit über diesen Terminal-Assistenten.
**Wenn du die Weboberfläche eingeschaltet hast, brauchst du die Shell-Befehle unten
für normale Einstellungsänderungen nicht.**

## 2. Im Browser bedienen

Öffne auf deinem PC oder Smartphone diese Adresse und ersetze `DEINE-LINUX-IP`
durch die IP-Adresse des Linux-Rechners mit dem Scanner:

```text
http://DEINE-LINUX-IP:8765
```

Die Adresse des MQTT-Brokers kann eine andere sein. Falls du im Assistenten einen
anderen Web-Port gewählt hast, verwende diesen statt `8765`.

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
auf **QR erstellen & Test starten**, scanne dann aber deinen vorhandenen Barcode.
Reine Ziffern reichen nicht immer aus, um ein Layout eindeutig zu erkennen.

### Beliebige Codes ansehen und kopieren

Öffne **Scannen**, klicke auf **Scannen starten** und scanne deine Codes nacheinander.
Jeder Eintrag hat einen **Kopieren**-Button. Mit **Beenden** kehrst du zum normalen
Versand an Home Assistant zurück.

Während der Aufnahme wird die Weitergabe an Home Assistant pausiert. Nach zwei
Minuten ohne neuen abgeschlossenen Scan endet die Pause automatisch. Die letzten
20 Einträge bleiben zum Kopieren erhalten; **Liste leeren** löscht sie ausdrücklich.
Beim Neustarten oder Neuladen des Empfangsdienstes geht diese lokale Liste verloren,
auch beim Speichern normaler Einstellungen. Ein Browser-Neuladen löscht sie nicht.

### Einstellungen ändern

Unter **Einrichtung** kannst du Scanner, MQTT-Verbindung und Gerätenamen ändern.
Klicke anschließend auf **Speichern und anwenden**. Warte kurz, bevor du wieder scannst.
Ein leeres Feld für das neue MQTT-Passwort erhält das bisherige Passwort.

Unter **Status** siehst du, ob Scanner und MQTT verbunden sind. Dort kannst du die
Weitergabe von Scans auch dauerhaft aus- oder wieder einschalten.

### Passwort, Sprache und Farben

- **Passwortschutz:** Unter **Einrichtung → Zugangsschutz** aktivieren, ein eigenes
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
2. Suche bei den MQTT-Geräten nach dem Namen aus dem Einrichtungsassistenten.
3. Dort erscheint der Sensor **Last scan** für den zuletzt gescannten Inhalt.
4. Beende eine eventuell laufende lokale Aufnahme im Tab **Scannen** und scanne
   einen normalen Barcode. Prüfe, ob er in Home Assistant ankommt.

Auch QR-Texte können übertragen werden. Lange Texte findest du im Sensorattribut
`barcode`. Jeder neue Scan erhält eine neue Scan-ID, auch wenn du denselben Code mehrfach scannst.

Für Automationen oder andere Anwendungen findest du das Nachrichtenformat unter
[Technischer Hintergrund](docs/TECHNICAL_de.md#mqtt-und-home-assistant).

## Updates und Hilfe

### Aktualisieren

Diesen Befehl im Terminal des Linux-Rechners als `root` ausführen:

```bash
myscanner update
```

Danach die Browserseite mit **Strg+F5** neu laden. Deine Einstellungen und wartenden
MQTT-Scans bleiben erhalten. Updates erfolgen nur auf deinen Aufruf hin.

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
Für dieselben Änderungen im Browser reicht der Tab **Einrichtung**.
Alle folgenden Befehle werden auf dem Linux-Rechner als `root` ausgeführt.

Den Einrichtungsassistenten erneut starten und bestehende Werte mit Enter behalten:

```bash
myscanner setup
```

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
