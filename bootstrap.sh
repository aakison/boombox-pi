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
  nano
  
git clone https://github.com/aakison/boombox-pi.git

# Copy configs
cp mpd/mpd.conf /etc/mpd.conf
cp audio/.asoundrc ~/.asoundrc
cp mounts/.smbcredentials ~/.smbcredentials
chmod 600 ~/.smbcredentials

# Enable services
sudo systemctl enable mpd
sudo systemctl restart mpd

# Mount shares
bash mounts/smb-mount.sh

# Setup Bluetooth
bash bluetooth/bt-setup.sh

echo "✅ Setup complete. Ready to stream and sync."
