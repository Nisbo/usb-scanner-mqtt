#!/usr/bin/env bash
# Debian/Ubuntu installer. Safe to run again; existing configuration is preserved.
set -euo pipefail
umask 077
REPOSITORY=Nisbo/usb-scanner-mqtt
INSTALL_DIR=/opt/usb-scanner-mqtt
CONFIG=/etc/usb-scanner-mqtt/config.json
UPDATE=false
SETUP_MODE=""
PINNED_REVISION=""
NON_INTERACTIVE=false
for argument in "$@"; do
  case "$argument" in
    --update) UPDATE=true ;;
    --revision=*) PINNED_REVISION=${argument#*=} ;;
    --non-interactive) NON_INTERACTIVE=true ;;
    --browser) SETUP_MODE=browser ;;
    --shell) SETUP_MODE=shell ;;
    *) echo 'Usage: install.sh [--update] [--browser|--shell] [--non-interactive]' >&2; exit 1 ;;
  esac
done
SETUP_TTY=false
if ! $NON_INTERACTIVE && { exec 8</dev/tty; } 2>/dev/null; then
  SETUP_TTY=true
fi
INSTALL_LANGUAGE=en
message() {
  if [[ $INSTALL_LANGUAGE == de ]]; then printf '%s' "$2"; else printf '%s' "$1"; fi
}
if $SETUP_TTY; then
  echo 'Choose language / Sprache wählen:'
  echo '  1. English (default)'
  echo '  2. Deutsch'
  while true; do
    printf 'Language / Sprache [1]: '
    if ! IFS= read -r language_choice <&8; then message Cancelled. Abgebrochen.; printf '\n'; exit 0; fi
    case "${language_choice:-1}" in
      1|en|English) INSTALL_LANGUAGE=en; break ;;
      2|de|Deutsch) INSTALL_LANGUAGE=de; break ;;
      *) echo 'Please choose 1 or 2 / Bitte 1 oder 2 wählen.' ;;
    esac
  done
fi
export USB_SCANNER_INSTALL_LANGUAGE="$INSTALL_LANGUAGE"
if [[ $(id -u) != 0 ]]; then
  { message 'Run the installer as root (or with sudo bash).' 'Installer als root ausführen (oder mit sudo bash).'; printf '\n'; } >&2
  exit 1
fi
if [[ $(uname -s) != Linux ]] || ! command -v apt-get >/dev/null || ! command -v systemctl >/dev/null; then
  { message 'This first version requires Debian/Ubuntu Linux with systemd.' 'Benötigt Debian/Ubuntu Linux mit systemd.'; printf '\n'; } >&2
  exit 1
fi
if $UPDATE && [[ ! -f $CONFIG ]]; then
  { message 'No configuration found. Run the installer without --update first.' 'Keine Einstellungen gefunden. Installer zuerst ohne --update ausführen.'; printf '\n'; } >&2
  exit 1
fi
exec 9>/run/lock/usb-scanner-mqtt.lock
if ! flock -n 9; then
  { message 'Another scanner installation/update is already running.' 'Eine andere Scannerinstallation oder Aktualisierung läuft bereits.'; printf '\n'; } >&2
  exit 1
fi
# Fetch current helpers too, so uninstall uses the selected language even when
# the installed version predates installer translations. No package changes here.
download_source() {
  staging=$(mktemp -d)
  trap 'rm -rf -- "$staging"' EXIT
  # Pin the whole download to one commit so an update cannot mix file versions.
  if [[ -n $PINNED_REVISION ]]; then
    commit=$PINNED_REVISION
  else
    channel=stable
    if [[ -f $CONFIG ]]; then
      channel=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("update_channel", "stable"))' "$CONFIG")
    fi
    case "$channel" in
      dev) reference=dev ;;
      stable|prerelease)
        if [[ $channel == stable ]]; then endpoint=releases/latest; else endpoint='releases?per_page=100'; fi
        reference=$(curl --fail --silent --show-error --location --retry 3 --connect-timeout 15 --max-time 90 \
          "https://api.github.com/repos/$REPOSITORY/$endpoint" | python3 -c '
import json,re,sys
value=json.load(sys.stdin)
def key(release):
 m=re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-(dev|alpha|beta|rc)(?:\.(\d+))?)?", release.get("tag_name", ""))
 if not m: return (-1,)
 a,b,c,stage,n=m.groups()
 return (int(a),int(b),int(c),{"dev":0,"alpha":1,"beta":2,"rc":3,None:4}[stage],int(n or 0))
if isinstance(value,list): value=max((r for r in value if not r.get("draft")),key=key)
tag=value["tag_name"]
if key(value)==(-1,): sys.exit("Invalid release tag")
print(tag)') ;;
      *) echo 'Invalid update channel.' >&2; exit 1 ;;
    esac
    commit=$(curl --fail --silent --show-error --location --retry 3 --connect-timeout 15 --max-time 90 \
      "https://api.github.com/repos/$REPOSITORY/commits/$reference" | \
      python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
  fi
  if [[ ! $commit =~ ^[a-f0-9]{40}$ ]]; then
    { message 'GitHub returned an invalid revision; installation was not changed.' 'GitHub lieferte eine ungültige Version; Installation unverändert.'; printf '\n'; } >&2
    exit 1
  fi
  if [[ -f $INSTALL_DIR/current/REVISION ]] && [[ $(cat "$INSTALL_DIR/current/REVISION") == "$commit" ]]; then
    message 'Application already up to date; checking installed files and service.' 'Programm bereits aktuell; Dateien und Dienst werden geprüft.'; printf '\n'
  fi
  curl --fail --silent --show-error --location --retry 3 --connect-timeout 15 --max-time 120 \
    "https://codeload.github.com/$REPOSITORY/tar.gz/$commit" -o "$staging/source.tar.gz"
  tar -xzf "$staging/source.tar.gz" -C "$staging"
  source_dir="$staging/usb-scanner-mqtt-$commit"
  [[ -f $source_dir/src/usb_scanner_mqtt/cli.py && -f $source_dir/usb-scanner-mqtt.service ]]
}
RESET_SETUP=false
if ! $UPDATE && [[ -f $CONFIG || -d $INSTALL_DIR/current || -x /usr/local/bin/myscanner ]]; then
  if $SETUP_TTY; then
    message 'Already installed:' 'Bereits installiert:'; printf '\n'
    message '  1. Update / repair; keep settings' '  1. Aktualisieren / reparieren; Einstellungen behalten'; printf '\n'
    message '  2. Reset setup and start again' '  2. Einrichtung zurücksetzen und neu beginnen'; printf '\n'
    message '  3. Uninstall' '  3. Deinstallieren'; printf '\n'
    message '  0. Exit' '  0. Beenden'; printf '\n'
    while true; do
      message 'Choice [1]: ' 'Auswahl [1]: '
      if ! IFS= read -r action <&8; then message Cancelled. Abgebrochen.; printf '\n'; exit 0; fi
      case "${action:-1}" in
        1) break ;;
        2)
          message 'Deletes ALL settings, passwords and queued scans.' 'Löscht ALLE Einstellungen, Passwörter und wartenden Scans.'; printf '\n'
          message 'Type DELETE to confirm: ' 'Zum Bestätigen DELETE eingeben: '
          if ! IFS= read -r confirmation <&8 || [[ $confirmation != DELETE ]]; then
            message Cancelled. Abgebrochen.; printf '\n'; exit 0
          fi
          RESET_SETUP=true; break ;;
        3)
          if [[ ! -x /usr/local/bin/myscanner ]]; then
            { message 'Command missing. Choose repair first.' 'Befehl fehlt. Zuerst reparieren.'; printf '\n'; } >&2; exit 1
          fi
          # The removal command acquires the same lock itself.
          flock -u 9
          download_source
          PYTHONPATH="$source_dir/src" python3 -m usb_scanner_mqtt --config "$CONFIG" uninstall <&8
          exit $? ;;
        0) message Cancelled. Abgebrochen.; printf '\n'; exit 0 ;;
        *) message 'Please choose 1, 2, 3 or 0.' 'Bitte 1, 2, 3 oder 0 wählen.'; printf '\n' ;;
      esac
    done
  else
    message 'No terminal available; keeping existing settings.' 'Kein Terminal verfügbar; Einstellungen bleiben erhalten.'; printf '\n'
  fi
fi
if [[ ! -f $CONFIG ]] || $RESET_SETUP; then
  if [[ -z $SETUP_MODE ]]; then
    if $SETUP_TTY; then
      message 'How would you like to set up?' 'Wie möchtest du einrichten?'; printf '\n'
      message '  1. Browser (recommended)' '  1. Browser (empfohlen)'; printf '\n'
      message '  2. Terminal' '  2. Terminal'; printf '\n'
      while true; do
        message 'Choice [1]: ' 'Auswahl [1]: '
        if ! IFS= read -r setup_choice <&8; then
          { message 'Setup cancelled: no input.' 'Einrichtung abgebrochen: keine Eingabe.'; printf '\n'; } >&2
          exit 1
        fi
        case "${setup_choice:-1}" in
          1) SETUP_MODE=browser; break ;;
          2) SETUP_MODE=shell; break ;;
          *) message 'Please choose 1 or 2.' 'Bitte 1 oder 2 wählen.'; printf '\n' ;;
        esac
      done
    else
      message 'No terminal available; preparing browser setup.' 'Kein Terminal verfügbar; Browser-Einrichtung wird vorbereitet.'; printf '\n'
      SETUP_MODE=browser
    fi
  fi
  if [[ $SETUP_MODE == shell ]] && ! $SETUP_TTY; then
    { message 'Terminal setup requires an interactive terminal.' 'Terminal-Einrichtung benötigt ein interaktives Terminal.'; printf '\n'; } >&2
    exit 1
  fi
fi
missing=()
for package in ca-certificates curl python3 python3-venv python3-evdev python3-paho-mqtt; do
  if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) != 'install ok installed' ]]; then
    missing+=("$package")
  fi
done
if ((${#missing[@]})); then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  { message 'Python 3.11 or newer is required.' 'Python 3.11 oder neuer wird benötigt.'; printf '\n'; } >&2
  exit 1
fi
download_source
# Validate the candidate before replacing any installed application or data.
if [[ -f $INSTALL_DIR/current/src/usb_scanner_mqtt/__init__.py ]] && ! $RESET_SETUP; then
  PYTHONPATH="$source_dir/src" python3 - "$INSTALL_DIR/current" "$commit" <<'GUARD'
import pathlib,re,sys
from usb_scanner_mqtt.updates import assess, revision
from usb_scanner_mqtt import __version__
root=pathlib.Path(sys.argv[1])
match=re.search(r'^__version__ = "([^"]+)"$', (root/'src/usb_scanner_mqtt/__init__.py').read_text(), re.M)
if not match: sys.exit('Cannot determine installed version; installation unchanged.')
result=assess({'channel':'stable','version':__version__,'revision':sys.argv[2]}, match[1], revision(root))
if not result['available'] and result['status']=='waiting':
 sys.exit('This channel has not caught up with your installed build. No downgrade; installation unchanged.')
GUARD
fi
install -d -m 0755 "$INSTALL_DIR" "$INSTALL_DIR/releases"
# evdev/Paho are Debian packages: no compiler or PyPI download is required.
# The receiver runs via its own interpreter; distro dependencies remain apt-managed.
if [[ ! -x $INSTALL_DIR/venv/bin/python ]]; then
  python3 -m venv --system-site-packages --without-pip "$INSTALL_DIR/venv"
fi
PYTHONPATH="$source_dir/src" "$INSTALL_DIR/venv/bin/python" -c \
  'import evdev, paho.mqtt.client; from usb_scanner_mqtt.cli import main'
# Reset only after the download and interpreter checks have succeeded.
if $RESET_SETUP; then
  systemctl stop usb-scanner-mqtt.service
  rm -rf -- /etc/usb-scanner-mqtt /var/lib/usb-scanner-mqtt
fi
if [[ -f $CONFIG ]]; then
  PYTHONPATH="$source_dir/src" "$INSTALL_DIR/venv/bin/python" -m usb_scanner_mqtt --config "$CONFIG" check-config
fi
release="$INSTALL_DIR/releases/$commit"
if [[ -d $release && ! -f $release/REVISION ]]; then
  # A power loss during an earlier copy must not leave an unrecoverable install.
  rm -rf -- "$release"
fi
if [[ -d $release ]] && { ! diff -qr -x __pycache__ -x '*.pyc' "$source_dir/src" "$release/src" >/dev/null 2>&1 || ! cmp -s "$source_dir/install.sh" "$release/install.sh"; }; then
  # Build a fresh copy; keep the running release untouched for rollback.
  release=$(mktemp -d "$INSTALL_DIR/releases/$commit-XXXXXXXX")
  rmdir "$release"
fi
if [[ ! -d $release ]]; then
  install -d -m 0755 "$release"
  cp -R "$source_dir/src" "$release/src"
  install -m 0644 "$source_dir/install.sh" "$release/install.sh"
  printf '%s\n' "$commit" > "$release/REVISION"
fi
old_release=$(readlink "$INSTALL_DIR/current" || true)
cat > "$staging/myscanner" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=/opt/usb-scanner-mqtt/current/src
exec /opt/usb-scanner-mqtt/venv/bin/python -m usb_scanner_mqtt "$@"
WRAPPER
install -m 0755 "$staging/myscanner" /usr/local/bin/myscanner
install -d -m 0700 /etc/usb-scanner-mqtt /var/lib/usb-scanner-mqtt
install -m 0644 "$source_dir/usb-scanner-mqtt.service" /etc/systemd/system/usb-scanner-mqtt.service
ln -sfn "$release" "$INSTALL_DIR/.current-next"
mv -Tf "$INSTALL_DIR/.current-next" "$INSTALL_DIR/current"
if [[ ! -f $CONFIG ]]; then
  if $SETUP_TTY; then
    /usr/local/bin/myscanner --config "$CONFIG" setup --mode "$SETUP_MODE" <&8
  else
    /usr/local/bin/myscanner --config "$CONFIG" setup --mode browser
  fi
else
  message 'Existing settings found; keeping configuration and queued scans. Setup is not run again.' 'Vorhandene Einstellungen und wartende Scans bleiben erhalten. Die Einrichtung wird nicht erneut gestartet.'; printf '\n'
fi
systemctl daemon-reload
systemctl enable usb-scanner-mqtt.service
if ! systemctl restart usb-scanner-mqtt.service; then
  if [[ -n $old_release && -d $old_release ]]; then
    ln -sfn "$old_release" "$INSTALL_DIR/.current-rollback"
    mv -Tf "$INSTALL_DIR/.current-rollback" "$INSTALL_DIR/current"
    systemctl restart usb-scanner-mqtt.service || true
  fi
  message 'Service restart failed; previous application restored where available.' 'Dienstneustart fehlgeschlagen; vorherige Programmversion soweit möglich wiederhergestellt.'; printf '\n' >&2
  exit 1
fi
sleep 2
if ! systemctl is-active --quiet usb-scanner-mqtt.service; then
  { message 'Service is not running. Check: myscanner logs' 'Dienst läuft nicht. Meldungen anzeigen: myscanner logs'; printf '\n'; } >&2
  exit 1
fi
# Keep current and previous application, without accumulating every old update.
for directory in "$INSTALL_DIR"/releases/*; do
  if [[ -d $directory && ! -L $directory && ${directory##*/} =~ ^[a-f0-9]{40}(-[a-zA-Z0-9]{8})?$ && $directory != "$release" && $directory != "$old_release" ]]; then
    rm -rf -- "$directory"
  fi
done
message 'Installed. Commands: myscanner status | myscanner web | myscanner update | myscanner uninstall' 'Installiert. Befehle: myscanner status | myscanner web | myscanner update | myscanner uninstall'; printf '\n'
/usr/local/bin/myscanner --config "$CONFIG" web
message 'After setup, open Home Assistant > Settings > Devices & services > MQTT and look for your scanner display name.' 'Nach der Einrichtung: Home Assistant > Einstellungen > Geräte & Dienste > MQTT öffnen und nach dem Anzeigenamen deines Scanners suchen.'; printf '\n'
