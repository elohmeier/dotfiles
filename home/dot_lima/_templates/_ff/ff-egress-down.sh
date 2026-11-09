#!/bin/sh
# Tear down ff-egress and restore the uplink. After a failure (SERVICE_RESULT != success)
# keep egress blocked until the next start: the entrypoint's kill switch if it got that far,
# otherwise the boot-time one.
if [ "${SERVICE_RESULT:-success}" != success ]; then
	nft list table inet ff_egress >/dev/null 2>&1 || nft -f /etc/ff-egress/killswitch.nft
	exit 0
fi
# shellcheck source=/dev/null
. "/profiles/${FF_PROFILE}/profile"
rm -f /run/ff-egress-ready
nft delete table inet ff_egress 2>/dev/null
nft delete table inet ff_killswitch 2>/dev/null
for l in /sys/class/net/wg_c* ${FF_CLIENT_INTERFACE:-} ${FF_MESH_INTERFACE:-} ${FF_PRIMARY_INTERFACE:-} ${FF_TUNNEL_INTERFACE:-}; do
	ip link del "${l##*/}" 2>/dev/null
done
while ip rule del priority 100 2>/dev/null; do :; done
while ip -6 rule del priority 100 2>/dev/null; do :; done
ln -sf ../run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
# systemd-networkd restores the uplink's default routes, which the entrypoints delete.
if [ -s /run/ff-egress-uplink ]; then
	networkctl reconfigure "$(cat /run/ff-egress-uplink)"
	for _ in $(seq 1 30); do
		ip -4 route show default | grep -q . && break
		sleep 1
	done
fi
true
