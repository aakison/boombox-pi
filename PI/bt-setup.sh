#!/bin/bash
bluetoothctl <<EOF
power on
agent on
default-agent
discoverable on
pairable on
EOF
