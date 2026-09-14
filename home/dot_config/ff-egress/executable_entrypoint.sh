#!/usr/bin/env bash
set -euo pipefail

profile="${FF_PROFILE:-ffhb}"
profile_file="/profiles/${profile}/profile"
[[ -f "${profile_file}" ]] || {
	echo "unknown Freifunk profile: ${profile}" >&2
	exit 1
}
# shellcheck source=/dev/null
source "${profile_file}"

if [[ "${FF_PROVIDER:-fastd}" != "fastd" ]]; then
	exec "/usr/local/bin/${FF_PROVIDER}-entrypoint.sh"
fi

state="/state/${profile}"
mkdir -p "${state}"
chmod 700 "${state}"
umask 077

secret_file="${state}/secret"
if [[ ! -s "${secret_file}" ]]; then
	fastd --generate-key --machine-readable | head -1 >"${secret_file}"
fi
mac_file="${state}/mac"
if [[ ! -s "${mac_file}" ]]; then
	bytes=$(od -An -N5 -tx1 /dev/urandom | tr -d ' \n')
	printf '02:%s:%s:%s:%s:%s\n' "${bytes:0:2}" "${bytes:2:2}" "${bytes:4:2}" "${bytes:6:2}" "${bytes:8:2}" >"${mac_file}"
fi

uplink_if=$(ip -4 route show default | awk 'NR == 1 {for (i=1; i<=NF; i++) if ($i == "dev") print $(i+1)}')
uplink_gw=$(ip -4 route show default | awk 'NR == 1 {for (i=1; i<=NF; i++) if ($i == "via") print $(i+1)}')
[[ -n "${uplink_if}" ]] || {
	echo "no IPv4 underlay route" >&2
	exit 1
}

fastd_conf="${state}/fastd.conf"
peer_ips=()
{
	printf 'log level info;\nmode tap;\ninterface "%s";\nmethod "%s";\nmtu %s;\nsecret "%s";\n' \
		"${FF_TUNNEL_INTERFACE}" "${FF_FASTD_METHOD}" "${FF_FASTD_MTU}" "$(<"${secret_file}")"
	echo 'peer group "backbone" {'
	echo '  peer limit 1;'
	while read -r name key host port; do
		[[ -n "${name}" ]] || continue
		ip=$(getent ahostsv4 "${host}" | awk '$2 == "STREAM" {print $1; exit}')
		[[ -n "${ip}" ]] || {
			echo "cannot resolve ${host}" >&2
			exit 1
		}
		peer_ips+=("${ip}")
		printf '  peer "%s" { key "%s"; remote %s:%s; }\n' "${name}" "${key}" "${ip}" "${port}"
	done <<<"${FF_PEERS}"
	echo '}'
} >"${fastd_conf}"

for ip in "${peer_ips[@]}"; do
	if [[ -n "${uplink_gw}" ]]; then
		ip route replace "${ip}/32" via "${uplink_gw}" dev "${uplink_if}"
	else
		ip route replace "${ip}/32" dev "${uplink_if}"
	fi
done

peer_set=$(printf '%s, ' "${peer_ips[@]}")
peer_set="${peer_set%, }"
nft -f - <<EOF
table inet ff_egress {
  set fastd4 { type ipv4_addr; elements = { ${peer_set} }; }
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
    oifname "${uplink_if}" ip daddr @fastd4 udp dport ${FF_FASTD_PORT} accept
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

fastd --config "${fastd_conf}" &
fastd_pid=$!
trap 'kill "${fastd_pid}" 2>/dev/null || true' TERM INT EXIT

for _ in $(seq 1 100); do
	[[ -e "/sys/class/net/${FF_TUNNEL_INTERFACE}" ]] && break
	sleep 0.1
done
[[ -e "/sys/class/net/${FF_TUNNEL_INTERFACE}" ]] || {
	echo "fastd did not create ${FF_TUNNEL_INTERFACE}" >&2
	exit 1
}
ip link set "${FF_TUNNEL_INTERFACE}" master "${FF_MESH_INTERFACE}"
ip link set "${FF_TUNNEL_INTERFACE}" up

for _ in $(seq 1 30); do
	batctl meshif "${FF_MESH_INTERFACE}" gateways | grep -q '^\* ' && break
	sleep 1
done
sleep 5

{
	for dns in ${FF_DNS_SERVERS}; do
		echo "nameserver ${dns}"
	done
} >"${state}/resolv.conf"
until udhcpc -f -q -n -t 30 -T 1 -i "${FF_CLIENT_INTERFACE}" -s /usr/local/bin/udhcpc-script; do
	sleep 1
done

touch /run/ff-egress-ready
wait "${fastd_pid}"
