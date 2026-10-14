#!/bin/sh

# systemd-binfmt flushes binfmt_misc on boot, dropping the WSLInterop handler
# registered by /init, so Windows .exe files fail with "Exec format error".

set -e

conf=/etc/binfmt.d/WSLInterop.conf

if [ -e "${conf}" ] || [ ! -d /run/systemd/system ]; then
	exit 0
fi

echo ':WSLInterop:M::MZ::/init:PF' | sudo tee "${conf}" >/dev/null
sudo systemctl restart systemd-binfmt
