#!/bin/bash
mkdir -p ~/mnt/music
sudo mount -t cifs //192.168.0.32/share_name ~/mnt/music \
  -o credentials=/home/pi/.smbcredentials,iocharset=utf8,uid=pi,gid=pi
