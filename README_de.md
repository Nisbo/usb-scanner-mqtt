# USB 2 MQTT Scanner

[English](README.md)

Scanne einen Barcode oder QR-Code und empfange den Inhalt in Home Assistant.
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

**Zuerst fragt die Installation, wie du einrichten möchtest:**

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

Öffne den angezeigten Link auf deinem PC oder Smartphone. Bei mehreren Adressen
verwende die deines Heimnetzes. Das ist die Adresse des Linux-Rechners bzw. der
VM/des Containers, nicht die des Proxmox-Hosts oder MQTT-Brokers.

Das Programm wartet, bis du im Browser Scanner und MQTT-Verbindung eingetragen und
**Speichern und anwenden** angeklickt hast. Erst dann startet der Scanempfang.

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

Ersetze `DEINE-LINUX-IP` durch die IP-Adresse des Linux-Rechners. Die Adresse des MQTT-Brokers kann eine andere sein. Falls du im Assistenten einen
anderen Web-Port gewählt hast, verwende diesen statt `8765`.

### Erste Einrichtung im Browser

Der Tab **Einrichtung** öffnet sich automatisch:

1. Wähle unter **Erkannte Geräte** deinen Scanner. Wähle keine normale Tastatur.
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

### Installationsbefehl erneut ausführen

Eine bestehende Einrichtung wird erkannt und erhalten. Der Assistent startet nicht
noch einmal; fehlende Pakete werden ergänzt und der veröffentlichte Programmstand
wird installiert. Der Dienst wird neu gestartet, auch wenn der Stand bereits aktuell
ist. Einstellungen und wartende MQTT-Scans bleiben erhalten; lokale Scanliste und
Web-Anmeldesitzungen gehen beim Dienstneustart verloren.

### Deinstallieren

Im Terminal als `root` ausführen:

```bash
myscanner uninstall
```

Wähle **1**, um nur das Programm zu entfernen und Einstellungen samt wartenden
Scans für eine spätere Neuinstallation zu behalten. **2** entfernt auch diese Daten
und die gespeicherten Passwörter. **0** bricht ab.

Die Entfernung muss bestätigt werden: bei Datenerhalt mit `yes`, beim vollständigen
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

Die Auswahl Browser/Terminal erneut öffnen:

```bash
myscanner setup
```

Oder den Terminal-Assistenten direkt starten:

```bash
myscanner setup --mode shell
```

### Der Terminal-Assistent

Die Fragen sind auf Englisch. Ein Wert in eckigen Klammern ist der Vorschlag;
**Enter behält ihn bei**. Bei vorhandener Einrichtung werden deine gespeicherten
Werte vorgeschlagen. Bei einer neuen Einrichtung gelten die unten genannten Startwerte.

| Frage | Bedeutung und Eingabe |
| --- | --- |
| `Scanner device: path or number` | Oberhalb der Frage stehen gefundene Eingabegeräte mit Nummer, Gerätename und Pfad. Gib die Nummer deines Scanners ein. Bei nur einem Gerät wird dessen Pfad vorbelegt. Ohne Treffer erscheint ein Hinweis; dann USB/Freigabe prüfen. |
| `Scanner ID` | Technische Kennung für MQTT. Vorschlag `usb-scanner-1`; erlaubt sind Buchstaben ohne Umlaute, Ziffern, Bindestrich und Unterstrich. |
| `Name shown in Home Assistant` | Frei wählbarer Anzeigename. Auch `Küche` und Leerzeichen funktionieren. |
| `Layout configured ON the scanner` | Startwert `us`, nicht automatisch erkannt. Bei Unkenntnis Enter drücken und anschließend im Browser kalibrieren. |
| `Output profile` | Legt fest, wie zusätzliche Zeichen gelesen werden. Startwert `standard`, nicht automatisch erkannt. Bei Unkenntnis Enter drücken; die Kalibrierung prüft das Profil mit. |
| `MQTT scan topic` | Adresse für Scanmeldungen. Wird aus der Kennung vorgeschlagen, etwa `usb-scanner-mqtt/usb-scanner-1/scan`. Meist Enter drücken. |
| `MQTT broker IP or hostname` | Nur Adresse oder Hostname des Brokers, ohne `http://`, `https://`, `mqtt://` und ohne Port. |
| `Use TLS?` | `yes` nur bei einem TLS-Zugang deines Brokers. Sonst den Vorschlag `no` übernehmen. |
| `MQTT port` | Häufig `1883` ohne TLS oder `8883` mit TLS. Verwende den tatsächlich am Broker eingerichteten Port. |
| `MQTT username` | Benutzername des vorhandenen Brokers. Verlangt er keine Anmeldung, `-` eingeben. |
| `MQTT password` | Wird bei einem Benutzernamen abgefragt. Die Eingabe ist unsichtbar; das ist normal. |
| `Custom CA certificate path` | Nur bei TLS: Für öffentlich vertrauenswürdige Zertifikate leer lassen; sonst den Pfad zur eigenen CA-Datei eintragen. |
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
