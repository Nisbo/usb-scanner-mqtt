#!/usr/bin/env bash
# Debian/Ubuntu installer. Safe to run again; existing configuration is preserved.
set -euo pipefail
umask 077
REPOSITORY=Nisbo/usb-scanner-mqtt
INSTALL_DIR=/opt/usb-scanner-mqtt
CONFIG=/etc/usb-scanner-mqtt/config.json
UPDATE=false
SETUP_MODE=""
for argument in "$@"; do
  case "$argument" in
    --update) UPDATE=true ;;
    --browser) SETUP_MODE=browser ;;
    --shell) SETUP_MODE=shell ;;
    *) echo 'Usage: install.sh [--update] [--browser|--shell]' >&2; exit 1 ;;
  esac
done
if [[ $(id -u) != 0 ]]; then
  echo 'Run the installer as root (or with sudo bash).' >&2
  exit 1
fi
if [[ $(uname -s) != Linux ]] || ! command -v apt-get >/dev/null || ! command -v systemctl >/dev/null; then
  echo 'This first version requires Debian/Ubuntu Linux with systemd.' >&2
  exit 1
fi
if $UPDATE && [[ ! -f $CONFIG ]]; then
  echo 'No configuration found. Run the installer without --update first.' >&2
  exit 1
fi
exec 9>/run/lock/usb-scanner-mqtt.lock
if ! flock -n 9; then
  echo 'Another scanner installation/update is already running.' >&2
  exit 1
fi
SETUP_TTY=false
RESET_SETUP=false
if { exec 8</dev/tty; } 2>/dev/null; then
  SETUP_TTY=true
fi
if ! $UPDATE && [[ -f $CONFIG || -d $INSTALL_DIR/current || -x /usr/local/bin/myscanner ]]; then
  if $SETUP_TTY; then
    echo 'Already installed / Bereits installiert:'
    echo '  1. Update / repair; keep settings / Aktualisieren / reparieren; Einstellungen behalten'
    echo '  2. Reset setup and start again / Einrichtung zurücksetzen und neu beginnen'
    echo '  3. Uninstall / Deinstallieren'
    echo '  0. Exit / Beenden'
    while true; do
      printf 'Choice / Auswahl [1]: '
      if ! IFS= read -r action <&8; then echo 'Cancelled / Abgebrochen.'; exit 0; fi
      case "${action:-1}" in
        1) break ;;
        2)
          echo 'Deletes ALL settings, passwords and queued scans. / Löscht ALLE Einstellungen, Passwörter und wartenden Scans.'
          printf 'Type DELETE to confirm / Zum Bestätigen DELETE eingeben: '
          if ! IFS= read -r confirmation <&8 || [[ $confirmation != DELETE ]]; then
            echo 'Cancelled / Abgebrochen.'; exit 0
          fi
          RESET_SETUP=true; break ;;
        3)
          if [[ ! -x /usr/local/bin/myscanner ]]; then
            echo 'Command missing. Choose repair first / Befehl fehlt. Zuerst reparieren.' >&2; exit 1
          fi
          # The removal command acquires the same lock itself.
          flock -u 9
          /usr/local/bin/myscanner --config "$CONFIG" uninstall <&8
          exit $? ;;
        0) echo 'Cancelled / Abgebrochen.'; exit 0 ;;
        *) echo 'Please choose 1, 2, 3 or 0.' ;;
      esac
    done
  else
    echo 'No terminal available; keeping existing settings. / Kein Terminal; Einstellungen bleiben erhalten.'
  fi
fi
if [[ ! -f $CONFIG ]] || $RESET_SETUP; then
  if [[ -z $SETUP_MODE ]]; then
    if $SETUP_TTY; then
      echo 'How would you like to set up? / Wie möchtest du einrichten?'
      echo '  1. Browser (recommended / empfohlen)'
      echo '  2. Terminal'
      while true; do
        printf 'Choice / Auswahl [1]: '
        if ! IFS= read -r setup_choice <&8; then
          echo 'Setup cancelled: no input.' >&2
          exit 1
        fi
        case "${setup_choice:-1}" in
          1) SETUP_MODE=browser; break ;;
          2) SETUP_MODE=shell; break ;;
          *) echo 'Please choose 1 or 2.' ;;
        esac
      done
    else
      echo 'No terminal available; preparing browser setup.'
      SETUP_MODE=browser
    fi
  fi
  if [[ $SETUP_MODE == shell ]] && ! $SETUP_TTY; then
    echo 'Terminal setup requires an interactive terminal.' >&2
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
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required.")'
staging=$(mktemp -d)
trap 'rm -rf -- "$staging"' EXIT
# Pin the whole download to one commit so an update cannot mix file versions.
commit=$(curl --fail --silent --show-error --location --retry 3 --connect-timeout 15 --max-time 90 \
  "https://api.github.com/repos/$REPOSITORY/commits/main" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
if [[ ! $commit =~ ^[a-f0-9]{40}$ ]]; then
  echo 'GitHub returned an invalid revision; installation was not changed.' >&2
  exit 1
fi
if [[ -f $INSTALL_DIR/current/REVISION ]] && [[ $(cat "$INSTALL_DIR/current/REVISION") == "$commit" ]]; then
  echo 'Application already up to date; checking installed files and service.'
fi
curl --fail --silent --show-error --location --retry 3 --connect-timeout 15 --max-time 120 \
  "https://codeload.github.com/$REPOSITORY/tar.gz/$commit" -o "$staging/source.tar.gz"
tar -xzf "$staging/source.tar.gz" -C "$staging"
source_dir="$staging/usb-scanner-mqtt-$commit"
[[ -f $source_dir/src/usb_scanner_mqtt/cli.py && -f $source_dir/usb-scanner-mqtt.service ]]
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
  echo 'Existing settings found; keeping configuration and queued scans. Setup is not run again.'
fi
systemctl daemon-reload
systemctl enable usb-scanner-mqtt.service
if ! systemctl restart usb-scanner-mqtt.service; then
  if [[ -n $old_release && -d $old_release ]]; then
    ln -sfn "$old_release" "$INSTALL_DIR/.current-rollback"
    mv -Tf "$INSTALL_DIR/.current-rollback" "$INSTALL_DIR/current"
    systemctl restart usb-scanner-mqtt.service || true
  fi
  echo 'Service restart failed; previous application restored where available.' >&2
  exit 1
fi
sleep 2
if ! systemctl is-active --quiet usb-scanner-mqtt.service; then
  echo 'Service is not running. Check: myscanner logs' >&2
  exit 1
fi
# Keep current and previous application, without accumulating every old update.
for directory in "$INSTALL_DIR"/releases/*; do
  if [[ -d $directory && ! -L $directory && ${directory##*/} =~ ^[a-f0-9]{40}$ && $directory != "$release" && $directory != "$old_release" ]]; then
    rm -rf -- "$directory"
  fi
done
echo 'Installed. Commands: myscanner status | myscanner web | myscanner update | myscanner uninstall'
/usr/local/bin/myscanner --config "$CONFIG" web
echo 'After setup, open Home Assistant > Settings > Devices & services > MQTT and look for your scanner display name.'
