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
  python3-pip \
  shairport-sync \
  samba \
  samba-common-bin

# vu-meter.py needs audioop, removed from the stdlib in Python 3.13+; this
# backport restores it. No-op if the interpreter still has it built in.
if ! python3 -c "import audioop" &>/dev/null; then
  sudo pip3 install --break-system-packages audioop-lts
fi

# Loopback device vu-meter.py reads from (see aloop.conf). Reload the module
# when its pinned options change so the new params take effect, then make
# sure it's loaded now and on every future boot.
if ! sudo cmp -s "$SCRIPT_DIR/aloop.conf" /etc/modprobe.d/aloop.conf 2>/dev/null; then
  sudo install -m 0644 "$SCRIPT_DIR/aloop.conf" /etc/modprobe.d/aloop.conf
  sudo modprobe -r snd-aloop 2>/dev/null || true
fi
lsmod | grep -q '^snd_aloop' || sudo modprobe snd-aloop
grep -qx snd-aloop /etc/modules || echo snd-aloop | sudo tee -a /etc/modules >/dev/null

# Copy a config file only when its content changed, restarting the given
# service(s) (if any) so unrelated services aren't bounced on every run.
install_config() {
  local src="$1" dest="$2"
  shift 2
  if ! sudo cmp -s "$src" "$dest" 2>/dev/null; then
    sudo install -m 0644 "$src" "$dest"
    for service in "$@"; do
      sudo systemctl restart "$service"
    done
  fi
}

# Install Raspotify (Spotify Connect) first, only if it isn't already
# installed, so the asound.conf restart list below can include it.
if ! dpkg -s raspotify &>/dev/null; then
  curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
fi
install_config "$SCRIPT_DIR/raspotify.conf" /etc/raspotify/conf raspotify

install_config "$SCRIPT_DIR/mpd.conf" /etc/mpd.conf mpd
# Every source shares this mixer, so a change here restarts all of them.
install_config "$SCRIPT_DIR/asound.conf" /etc/asound.conf mpd raspotify shairport-sync
# AirPlay discovery name. Installed after asound.conf so a config-triggered
# restart uses the shared mixer. Unchanged files do not restart the service.
install_config "$SCRIPT_DIR/shairport-sync.conf" /etc/shairport-sync.conf shairport-sync

sudo systemctl enable mpd
sudo systemctl enable shairport-sync

# Share /srv/music over SMB so other devices can drop music onto the Pi
bash "$SCRIPT_DIR/smb-share.sh"

# Setup Bluetooth
bash "$SCRIPT_DIR/bt-setup.sh"

echo "✅ Setup complete. Ready to stream and sync."
