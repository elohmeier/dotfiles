#!/bin/bash
set -eux -o pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y batctl bird2 fastd radvd wireguard-tools
echo batman_adv >/etc/modules-load.d/batman-adv.conf
modprobe batman_adv
