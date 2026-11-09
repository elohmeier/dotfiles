#!/bin/bash
set -eux -o pipefail
# shellcheck source=/dev/null
. "/profiles/${PARAM_FF_PROFILE}/profile"
pkgs=(curl iproute2 iputils-ping jq nftables)
case "${FF_PROVIDER:-fastd}" in
parker) pkgs+=(signify-openbsd wireguard-tools) mods=() ;;
fastd) pkgs+=(batctl fastd udhcpc) mods=(batman_adv) ;;
tunneldigger) pkgs+=(batctl udhcpc build-essential cmake git libnl-3-dev libnl-genl-3-dev pkg-config) mods=(batman_adv l2tp_core l2tp_netlink l2tp_eth) ;;
esac
dpkg -s "${pkgs[@]}" >/dev/null 2>&1 || {
	apt-get update
	DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkgs[@]}"
}
# From here on egress stays blocked unless the tunnel is up, also if anything below fails.
# Only on first setup: on later boots the unit has done this, and ff-egress has replaced it.
if ! systemctl is-enabled -q ff-egress-killswitch.service; then
	nft -f /etc/ff-egress/killswitch.nft
	systemctl enable ff-egress-killswitch.service
fi
# Cloud kernels lack batman_adv: base the VM on a generic image (see freifunk.yaml).
if ((${#mods[@]})); then
	modprobe -a "${mods[@]}"
	printf "%s\n" "${mods[@]}" >/etc/modules-load.d/ff-egress.conf
fi
if [[ "${FF_PROVIDER}" == tunneldigger && ! -x /usr/local/bin/tunneldigger ]]; then
	src=$(mktemp -d)
	git clone https://github.com/wlanslovenija/tunneldigger.git "${src}"
	git -C "${src}" checkout "${PARAM_FF_TUNNELDIGGER_COMMIT}"
	cmake -S "${src}/client" -B "${src}/build" -DUSE_LIBNL=TRUE -DCMAKE_C_FLAGS=-DHAVE_PTHREAD=1
	cmake --build "${src}/build"
	install "${src}/build/tunneldigger" /usr/local/bin/
	rm -rf "${src}"
fi
# Rank the uplink's RA routes below any tunnel or mesh route (fastd/tunneldigger get IPv6 via RAs).
# Restart networkd only when that changes: this runs on every boot, after ff-egress is up.
# Restart rather than reload: a just-upgraded networkctl may not talk to the running daemon.
uplink=$(cat /run/ff-egress-uplink 2>/dev/null || ip -j -4 route show default | jq -r ".[0].dev")
network_file=$(networkctl status "${uplink}" | awk '/Network File:/ {print $3}')
dropin="/etc/systemd/network/${network_file##*/}.d/ff-egress.conf"
if [[ ! -e "${dropin}" ]]; then
	mkdir -p "${dropin%/*}"
	printf '[IPv6AcceptRA]\nRouteMetric=2048\n' >"${dropin}"
	systemctl restart systemd-networkd
fi
mkdir -p /var/lib/ff-egress
ln -sfn /var/lib/ff-egress /state
systemctl daemon-reload
systemctl enable --now "ff-egress@${PARAM_FF_PROFILE}"
