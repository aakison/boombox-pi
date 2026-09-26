#!/bin/bash
# Publishes /srv/music as a local SMB share so other devices can drop music
# onto the Pi. Weak, hard-coded creds are acceptable: local network only.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE_USER=boombox
SHARE_PASS=boombox
SHARE_DIR=/srv/music
SHARE_CONF=/etc/samba/smb-boombox.conf
RESTART_SMB=

sudo mkdir -p "$SHARE_DIR"

getent group "$SHARE_USER" >/dev/null || sudo groupadd "$SHARE_USER"
id -u "$SHARE_USER" >/dev/null 2>&1 || \
  sudo useradd -M -N -g "$SHARE_USER" -s /usr/sbin/nologin -d "$SHARE_DIR" "$SHARE_USER"

sudo chown -R "$SHARE_USER:$SHARE_USER" "$SHARE_DIR"
sudo chmod 2775 "$SHARE_DIR"

# Re-running this just resets the same password, so it's safe every time.
printf '%s\n%s\n' "$SHARE_PASS" "$SHARE_PASS" | sudo smbpasswd -s -a "$SHARE_USER" >/dev/null
sudo smbpasswd -e "$SHARE_USER" >/dev/null

if ! sudo cmp -s "$SCRIPT_DIR/smb-share.conf" "$SHARE_CONF" 2>/dev/null; then
  sudo install -m 0644 "$SCRIPT_DIR/smb-share.conf" "$SHARE_CONF"
  RESTART_SMB=1
fi

if ! sudo grep -qF "include = $SHARE_CONF" /etc/samba/smb.conf; then
  printf '\ninclude = %s\n' "$SHARE_CONF" | sudo tee -a /etc/samba/smb.conf >/dev/null
  RESTART_SMB=1
fi

sudo systemctl enable smbd
[[ -n "$RESTART_SMB" ]] && sudo systemctl restart smbd

exit 0
