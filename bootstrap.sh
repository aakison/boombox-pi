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

# Install Raspotify (Spotify Connect)
curl -sL https://dtcooper.github.io/raspotify/install.sh | sh

# Configure Raspotify
sudo cp bootstrap-pi/raspotify.conf /etc/raspotify/conf
sudo systemctl restart raspotify

# Mount shares
bash mounts/smb-mount.sh

# Setup Bluetooth
bash bluetooth/bt-setup.sh

echo "✅ Setup complete. Ready to stream and sync."
