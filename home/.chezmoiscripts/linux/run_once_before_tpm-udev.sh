#!/bin/sh
[ -e /dev/tpmrm0 ] || exit 0
[ -r /dev/tpmrm0 ] && exit 0
sudo mkdir -p /etc/udev/rules.d
echo 'KERNEL=="tpmrm[0-9]*", MODE="0660", GROUP="wheel"' | sudo tee /etc/udev/rules.d/99-tpm.rules
sudo udevadm control --reload-rules
sudo udevadm trigger /dev/tpmrm0
