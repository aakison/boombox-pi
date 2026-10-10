#!/bin/bash
set -e

echo "🔧 Setting up Raspberry Pi audio stack..."

# Run from the cloned repo, so config files can be found regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo apt-get update
sudo apt-get install -y \
  alsa-utils \
  mpd \
  mpc \
  git \
  nano \
  python3-rpi.gpio \
  python3-numpy \
  python3-smbus \
  python3-pil \
  fonts-dejavu-core \
  i2c-tools \
  shairport-sync \
  samba \
  samba-common-bin

# Copy a config file only when its content changed, restarting the given
# service (if any) so unrelated services aren't bounced on every run.
install_config() {
  local src="$1" dest="$2" service="$3"
  if ! sudo cmp -s "$src" "$dest" 2>/dev/null; then
    sudo install -m 0644 "$src" "$dest"
    [[ -n "$service" ]] && sudo systemctl restart "$service"
  fi
}

install_config "$SCRIPT_DIR/mpd.conf" /etc/mpd.conf mpd
install_config "$SCRIPT_DIR/asound.conf" /etc/asound.conf mpd
# AirPlay discovery name. Installed after asound.conf so a config-triggered
# restart uses the shared mixer. Unchanged files do not restart the service.
install_config "$SCRIPT_DIR/shairport-sync.conf" /etc/shairport-sync.conf shairport-sync

sudo systemctl enable mpd
sudo systemctl enable shairport-sync

# Install Raspotify (Spotify Connect) only if it isn't already installed
if ! dpkg -s raspotify &>/dev/null; then
  curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
fi

# Configure Raspotify
install_config "$SCRIPT_DIR/raspotify.conf" /etc/raspotify/conf raspotify

# Share /srv/music over SMB so other devices can drop music onto the Pi
bash "$SCRIPT_DIR/smb-share.sh"

# Setup Bluetooth
bash "$SCRIPT_DIR/bt-setup.sh"

# Run boombox.py as a systemd service so it starts automatically on boot
BOOMBOX_USER="${SUDO_USER:-$USER}"
BOOMBOX_SERVICE_FILE="$(mktemp)"
cat > "$BOOMBOX_SERVICE_FILE" <<EOF
[Unit]
Description=Boombox control service
After=sound.target network.target

[Service]
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/boombox.py
WorkingDirectory=${SCRIPT_DIR}
User=${BOOMBOX_USER}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

if ! sudo cmp -s "$BOOMBOX_SERVICE_FILE" /etc/systemd/system/boombox.service 2>/dev/null; then
  sudo install -m 0644 "$BOOMBOX_SERVICE_FILE" /etc/systemd/system/boombox.service
  sudo systemctl daemon-reload
fi
rm -f "$BOOMBOX_SERVICE_FILE"

sudo systemctl enable boombox
sudo systemctl restart boombox

echo "✅ Setup complete. Ready to stream and sync."
