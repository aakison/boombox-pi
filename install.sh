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

# Mount shares
bash "$SCRIPT_DIR/smb-mount.sh"

# Setup Bluetooth
bash "$SCRIPT_DIR/bt-setup.sh"

echo "✅ Setup complete. Ready to stream and sync."
