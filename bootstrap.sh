#!/bin/bash
set -e

echo "🔧 Setting up Raspberry Pi audio stack..."



sudo apt-get update
sudo apt-get install -y \
  alsa-utils \
  mpd \
  mpc \
  speaker-test \
  git \
  nano \
  python3-rpi.gpio

git clone https://github.com/aakison/boombox-pi.git

# Copy configs
cp bootstrap-pi/mpd.conf /etc/mpd.conf
cp bootstrap-pi/asound.conf /etc/asound.conf


# Enable services
sudo systemctl enable mpd
sudo systemctl restart mpd

# Mount shares
bash mounts/smb-mount.sh

# Setup Bluetooth
bash bluetooth/bt-setup.sh

echo "✅ Setup complete. Ready to stream and sync."
