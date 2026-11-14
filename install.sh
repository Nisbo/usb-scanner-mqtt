#!/usr/bin/env bash
# Debian/Ubuntu installer. Safe to run again; existing configuration is preserved.
set -euo pipefail
umask 077
REPOSITORY=Nisbo/usb-scanner-mqtt
INSTALL_DIR=/opt/usb-scanner-mqtt
CONFIG=/etc/usb-scanner-mqtt/config.json
UPDATE=false
case "${1:-}" in
  "") ;;
  --update) UPDATE=true ;;
  *) echo 'Usage: install.sh [--update]' >&2; exit 1 ;;
esac
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
  if [[ ! -r /dev/tty ]]; then
    echo 'No terminal available. Run: myscanner setup; systemctl enable --now usb-scanner-mqtt' >&2
    exit 1
  fi
  /usr/local/bin/myscanner setup </dev/tty
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
echo 'Installed. Commands: myscanner status | myscanner test | myscanner logs | myscanner update'
echo 'HA: Settings > Devices & services > MQTT. Scan messages are never retained.'
