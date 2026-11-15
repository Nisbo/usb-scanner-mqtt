"""Installer language, scoped to the invoking process, separate from browser preferences."""
import os

DE = {'Browser setup selected. Wait for installation to finish, then open a link below.': 'Browser-Einrichtung '
                                                                                     'gewählt. '
                                                                                     'Nach '
                                                                                     'Abschluss '
                                                                                     'der '
                                                                                     'Installation '
                                                                                     'einen der '
                                                                                     'Links unten '
                                                                                     'öffnen.',
 'USB Scanner MQTT — setup (press Enter to keep an existing value)': 'USB Scanner MQTT — '
                                                                     'Einrichtung (Enter übernimmt '
                                                                     'den vorgeschlagenen Wert)',
 'Detected input devices (choose your scanner, not a regular keyboard):': 'Erkannte Eingabegeräte '
                                                                          '(Scanner auswählen, '
                                                                          'keine normale '
                                                                          'Tastatur):',
 'No input devices found. Check USB/passthrough or enter the device path manually.': 'Keine '
                                                                                     'Eingabegeräte '
                                                                                     'gefunden. '
                                                                                     'USB-Verbindung '
                                                                                     'bzw. '
                                                                                     'Gerätefreigabe '
                                                                                     'prüfen oder '
                                                                                     'Gerätepfad '
                                                                                     'eingeben.',
 'Scanner device: path or number': 'Scannergerät: Pfad oder Nummer',
 'Scanner ID (unique across your scanners)': 'Scannerkennung (für jeden Scanner eindeutig)',
 'Name shown in Home Assistant': 'Anzeigename in Home Assistant',
 'Keyboard layout: fixed starting value, not auto-detected. If unsure, keep it and use browser calibration later.': 'Tastaturlayout: '
                                                                                                                    'Startwert, '
                                                                                                                    'nicht '
                                                                                                                    'automatisch '
                                                                                                                    'erkannt. '
                                                                                                                    'Bei '
                                                                                                                    'Unsicherheit '
                                                                                                                    'übernehmen '
                                                                                                                    'und '
                                                                                                                    'später '
                                                                                                                    'im '
                                                                                                                    'Browser '
                                                                                                                    'kalibrieren.',
 'Layout configured ON the scanner (us/de/gb/fr/es)': 'AM Scanner eingestelltes Layout '
                                                      '(us/de/gb/fr/es)',
 'Output profile: how extra characters are read. Keep standard if unsure; calibration checks it.': 'Ausgabeprofil: '
                                                                                                   'bestimmt '
                                                                                                   'das '
                                                                                                   'Lesen '
                                                                                                   'zusätzlicher '
                                                                                                   'Zeichen. '
                                                                                                   'Bei '
                                                                                                   'Unsicherheit '
                                                                                                   'standard '
                                                                                                   'übernehmen '
                                                                                                   'und '
                                                                                                   'später '
                                                                                                   'kalibrieren.',
 'Output profile (standard/alt-pair-latin1)': 'Ausgabeprofil (standard/alt-pair-latin1)',
 'Scan topic: MQTT address used for scan messages. The suggested topic is generated from the scanner ID.': 'Scan-Topic: '
                                                                                                           'MQTT-Adresse '
                                                                                                           'für '
                                                                                                           'Scans. '
                                                                                                           'Der '
                                                                                                           'Vorschlag '
                                                                                                           'wird '
                                                                                                           'aus '
                                                                                                           'der '
                                                                                                           'Scannerkennung '
                                                                                                           'erzeugt.',
 'MQTT scan topic': 'MQTT-Scan-Topic',
 'Broker address: hostname or IP only, without http://, https://, mqtt:// or a port.': 'Brokeradresse: '
                                                                                       'nur '
                                                                                       'Hostname '
                                                                                       'oder IP, '
                                                                                       'ohne '
                                                                                       'http://, '
                                                                                       'https://, '
                                                                                       'mqtt:// '
                                                                                       'und ohne '
                                                                                       'Port.',
 'MQTT broker IP or hostname': 'IP-Adresse oder Hostname des MQTT-Brokers',
 'Use TLS only if your broker provides a TLS connection; usually port 8883 instead of 1883.': 'TLS '
                                                                                              'nur '
                                                                                              'nutzen, '
                                                                                              'wenn '
                                                                                              'dein '
                                                                                              'Broker '
                                                                                              'dies '
                                                                                              'anbietet; '
                                                                                              'meist '
                                                                                              'Port '
                                                                                              '8883 '
                                                                                              'statt '
                                                                                              '1883.',
 'Use TLS? (yes/no)': 'TLS verwenden? (ja/nein)',
 'MQTT port': 'MQTT-Port',
 "MQTT username (use '-' for no authentication)": "MQTT-Benutzername ('-' für keine Anmeldung)",
 'MQTT password (Enter keeps existing password): ': 'MQTT-Passwort (Enter behält das bisherige '
                                                    'Passwort): ',
 "Custom CA certificate path (or '-' for system certificates)": 'Pfad zur eigenen CA-Datei (oder '
                                                                "'-' für Systemzertifikate)",
 'Enable internal web interface? (yes/no)': 'Weboberfläche einschalten? (ja/nein)',
 'Web bind address': 'Web-Zugriffsadresse',
 'Web port': 'Web-Port',
 'Send scans over MQTT? (yes/no; no discards new test scans)': 'Scans über MQTT senden? (ja/nein; '
                                                               'nein verwirft neue Testscans)',
 'The receiver uses the selected scanner exclusively while running.': 'Der ausgewählte Scanner '
                                                                      'wird während des Betriebs '
                                                                      'ausschließlich von diesem '
                                                                      'Programm verwendet.',
 'USB passthrough must already be configured if this runs inside an LXC/VM.': 'Bei LXC/VM muss der '
                                                                              'Scanner bereits für '
                                                                              'diesen Container '
                                                                              'bzw. diese VM '
                                                                              'freigegeben sein.',
 'Web interface is off. Enable it with: myscanner set gui true': 'Weboberfläche ist ausgeschaltet. '
                                                                 'Einschalten mit: myscanner set '
                                                                 'gui true',
 '\nOpen one of these links in your browser to continue setup:': '\n'
                                                                 'Öffne einen dieser Links im '
                                                                 'Browser, um die Einrichtung '
                                                                 'fortzusetzen:',
 'Open this link in a browser on this Linux computer.': 'Öffne diesen Link in einem Browser direkt '
                                                        'auf diesem Linux-Rechner.',
 'Another installation, update or removal is running.': 'Eine andere Installation, Aktualisierung '
                                                        'oder Deinstallation läuft bereits.',
 'Cannot determine service status; nothing was removed.': 'Dienststatus konnte nicht ermittelt '
                                                          'werden; es wurde nichts entfernt.',
 'Program removed. ': 'Programm entfernt. ',
 'Settings and queued scans deleted.': 'Einstellungen und wartende Scans gelöscht.',
 'Settings and queued scans kept for reinstallation.': 'Einstellungen und wartende Scans für eine '
                                                       'erneute Installation behalten.',
 'Shared system packages and Proxmox settings were not removed. Remove the old MQTT device in Home Assistant manually if desired.': 'Gemeinsame '
                                                                                                                                    'Systempakete '
                                                                                                                                    'und '
                                                                                                                                    'Proxmox-Einstellungen '
                                                                                                                                    'bleiben '
                                                                                                                                    'erhalten. '
                                                                                                                                    'Das '
                                                                                                                                    'alte '
                                                                                                                                    'MQTT-Gerät '
                                                                                                                                    'kannst '
                                                                                                                                    'du '
                                                                                                                                    'bei '
                                                                                                                                    'Bedarf '
                                                                                                                                    'in '
                                                                                                                                    'Home '
                                                                                                                                    'Assistant '
                                                                                                                                    'löschen.',
 '1. Remove program; keep settings and queued scans (recommended)': '1. Programm entfernen; '
                                                                    'Einstellungen und wartende '
                                                                    'Scans behalten (empfohlen)',
 '2. Remove program AND all settings and queued scans': '2. Programm UND alle Einstellungen und '
                                                        'wartenden Scans entfernen',
 '0. Cancel': '0. Abbrechen',
 'Choice [1]: ': 'Auswahl [1]: ',
 'Cancelled.': 'Abgebrochen.',
 'Choose 1, 2 or 0.': 'Bitte 1, 2 oder 0 wählen.',
 'This stops the scanner service.': 'Der Scannerdienst wird gestoppt.',
 ' All settings, passwords and queued scans will be deleted.': ' Alle Einstellungen, Passwörter '
                                                               'und wartenden Scans werden '
                                                               'gelöscht.',
 ' Settings and queued scans will be kept.': ' Einstellungen und wartende Scans bleiben erhalten.',
 'yes': 'ja',
 'no': 'nein',
 'Configuration saved: {path} (permissions 0600).': 'Einstellungen gespeichert: {path}.',
 'Type {confirmation} to confirm: ': 'Zum Bestätigen {confirmation} eingeben: ',
 'Configuration valid.': 'Einstellungen sind gültig.'}


def text(message):
    return DE.get(message, message) if os.environ.get('USB_SCANNER_INSTALL_LANGUAGE') == 'de' else message
