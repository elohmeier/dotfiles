#!/usr/bin/env bash
set -euo pipefail

profile="${FF_PROFILE:-ffnw}"
# shellcheck source=/dev/null
source "/profiles/${profile}/profile"
state="/state/${profile}"
mkdir -p "${state}"
chmod 700 "${state}"
umask 077

uuid_file="${state}/uuid"
[[ -s "${uuid_file}" ]] || od -An -N16 -tx1 /dev/urandom | tr -d ' \n' >"${uuid_file}"
mac_file="${state}/mac"
if [[ ! -s "${mac_file}" ]]; then
	bytes=$(od -An -N5 -tx1 /dev/urandom | tr -d ' \n')
	printf '02:%s:%s:%s:%s:%s\n' "${bytes:0:2}" "${bytes:2:2}" "${bytes:4:2}" "${bytes:6:2}" "${bytes:8:2}" >"${mac_file}"
fi

uplink_if=$(ip -4 route show default | awk 'NR == 1 {for (i=1; i<=NF; i++) if ($i == "dev") print $(i+1)}')
uplink_gw=$(ip -4 route show default | awk 'NR == 1 {for (i=1; i<=NF; i++) if ($i == "via") print $(i+1)}')
broker_ip=$(getent ahostsv4 "${FF_TUNNELDIGGER_HOST}" | awk '$2 == "STREAM" {print $1; exit}')
[[ -n "${uplink_if}" && -n "${broker_ip}" ]]
if [[ -n "${uplink_gw}" ]]; then
	ip route replace "${broker_ip}/32" via "${uplink_gw}" dev "${uplink_if}"
else
	ip route replace "${broker_ip}/32" dev "${uplink_if}"
fi
ip route del default
ip -6 route flush default

nft -f - <<EOF
table inet ff_egress {
  chain input {
    type filter hook input priority filter; policy drop;
    iifname "lo" accept
    ct state established,related accept
    iifname "${FF_CLIENT_INTERFACE}" udp sport 67 udp dport 68 accept
    iifname "${FF_CLIENT_INTERFACE}" meta l4proto 58 accept
  }
  chain output {
    type filter hook output priority filter; policy drop;
    oifname "lo" accept
    oifname "${FF_CLIENT_INTERFACE}" accept
    oifname "${uplink_if}" ip daddr ${broker_ip} udp dport ${FF_TUNNELDIGGER_PORT} accept
  }
}
EOF

ip link add "${FF_MESH_INTERFACE}" type batadv ra "${FF_BATMAN_ALGORITHM}"
ip link add "${FF_PRIMARY_INTERFACE}" type dummy
ip link set "${FF_PRIMARY_INTERFACE}" address "$(<"${mac_file}")" mtu 1532 up
ip link set "${FF_PRIMARY_INTERFACE}" master "${FF_MESH_INTERFACE}"
ip link add "${FF_CLIENT_INTERFACE}" type bridge
ip link set "${FF_MESH_INTERFACE}" master "${FF_CLIENT_INTERFACE}"
ip link set "${FF_MESH_INTERFACE}" up
ip link set "${FF_CLIENT_INTERFACE}" up
batctl meshif "${FF_MESH_INTERFACE}" gw_mode client
batctl meshif "${FF_MESH_INTERFACE}" orig_interval "${FF_ORIG_INTERVAL}"
batctl meshif "${FF_MESH_INTERFACE}" hop_penalty "${FF_HOP_PENALTY}"

tunneldigger -f -u "$(<"${uuid_file}")" -b "${broker_ip}:${FF_TUNNELDIGGER_PORT}" \
	-i "${FF_TUNNEL_INTERFACE}" -I "${uplink_if}" &
tunneldigger_pid=$!
trap 'kill "${tunneldigger_pid}" 2>/dev/null || true' TERM INT EXIT

for _ in $(seq 1 300); do
	[[ -e "/sys/class/net/${FF_TUNNEL_INTERFACE}" ]] && break
	! kill -0 "${tunneldigger_pid}" 2>/dev/null && wait "${tunneldigger_pid}"
	sleep 0.1
done
[[ -e "/sys/class/net/${FF_TUNNEL_INTERFACE}" ]]
ip link set "${FF_TUNNEL_INTERFACE}" mtu "${FF_TUNNEL_MTU}"
ip link set "${FF_TUNNEL_INTERFACE}" master "${FF_MESH_INTERFACE}"
ip link set "${FF_TUNNEL_INTERFACE}" up

for _ in $(seq 1 30); do
	batctl meshif "${FF_MESH_INTERFACE}" gateways | grep -q '^\* ' && break
	sleep 1
done
{
	for dns in ${FF_DNS_SERVERS}; do echo "nameserver ${dns}"; done
} >"${state}/resolv.conf"
until udhcpc -f -q -n -t 30 -T 1 -i "${FF_CLIENT_INTERFACE}" -s /usr/local/bin/udhcpc-script; do
	sleep 1
done

touch /run/ff-egress-ready
wait "${tunneldigger_pid}"
