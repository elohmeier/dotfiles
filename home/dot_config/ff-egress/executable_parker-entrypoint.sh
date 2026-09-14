#!/usr/bin/env bash
set -euo pipefail

profile="${FF_PROFILE:-ffbs}"
# shellcheck source=/dev/null
source "/profiles/${profile}/profile"
state="/state/${profile}"
mkdir -p "${state}"
chmod 700 "${state}"
umask 077

key="${state}/wireguard.key"
[[ -s "${key}" ]] || wg genkey >"${key}"
pubkey=$(wg pubkey <"${key}")
nonce=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
response="${state}/response"
config="${state}/config.json"

curl --fail --silent --show-error --get "http://${FF_CONFIG_SERVER}/config" \
	--data-urlencode "pubkey=${pubkey}" \
	--data-urlencode "nonce=${nonce}" \
	--data-urlencode "v6mtu=1280" \
	--data-urlencode "version=ff-egress/1" >"${response}"
sed '$d' "${response}" >"${config}"
{
	echo "untrusted comment: signify public key"
	echo "${FF_CONFIG_PUBKEY}"
} >"${state}/config.pub"
{
	echo "untrusted comment: signed configuration"
	printf '%s\n' "$(tail -n 1 "${response}")"
} >"${state}/config.sig"
signify-openbsd -V -q -p "${state}/config.pub" -x "${state}/config.sig" -m "${config}"
[[ "$(jq -r .nonce "${config}")" == "${nonce}" ]]

uplink_if=$(ip -4 route show default | awk 'NR == 1 {for (i=1; i<=NF; i++) if ($i == "dev") print $(i+1)}')
uplink_gw=$(ip -4 route show default | awk 'NR == 1 {for (i=1; i<=NF; i++) if ($i == "via") print $(i+1)}')
[[ -n "${uplink_if}" ]]
route_underlay() {
	if [[ -n "${uplink_gw}" ]]; then
		ip route replace "$1/32" via "${uplink_gw}" dev "${uplink_if}"
	else
		ip route replace "$1/32" dev "${uplink_if}"
	fi
}

mapfile -t config_ips < <(getent ahostsv4 "${FF_CONFIG_SERVER}" | awk '$2 == "STREAM" {print $1}' | sort -u)
for ip in "${config_ips[@]}"; do route_underlay "${ip}"; done

declare -a interfaces endpoints endpoint_ips endpoint_ports gateways4 gateways6
while IFS=$'\t' read -r id endpoint gateway4 gateway6; do
	interface="wg_c${id}"
	endpoint_ip=${endpoint%:*}
	endpoint_port=${endpoint##*:}
	interfaces+=("${interface}")
	endpoints+=("${endpoint}")
	endpoint_ips+=("${endpoint_ip}")
	endpoint_ports+=("${endpoint_port}")
	gateways4+=("${gateway4}")
	gateways6+=("${gateway6}")
	route_underlay "${endpoint_ip}"
done < <(jq -r '.concentrators[] | [.id,.endpoint,.address4,.address6] | @tsv' "${config}")

{
	echo 'table inet ff_egress {'
	echo '  chain input {'
	echo '    type filter hook input priority filter; policy drop;'
	echo '    iifname "lo" accept'
	echo '    ct state established,related accept'
	echo '  }'
	echo '  chain output {'
	echo '    type filter hook output priority filter; policy drop;'
	echo '    oifname "lo" accept'
	for interface in "${interfaces[@]}"; do printf '    oifname "%s" accept\n' "${interface}"; done
	for i in "${!endpoint_ips[@]}"; do
		printf '    oifname "%s" ip daddr %s udp dport %s accept\n' "${uplink_if}" "${endpoint_ips[i]}" "${endpoint_ports[i]}"
	done
	echo '  }'
	echo '}'
} | nft -f -

address4=$(jq -r .address4 "${config}")
address6=$(jq -r .address6 "${config}")
mtu=$(jq -r .mtu "${config}")
keepalive=$(jq -r .wg_keepalive "${config}")
for i in "${!interfaces[@]}"; do
	interface=${interfaces[i]}
	peer=$(jq -r ".concentrators[$i].pubkey" "${config}")
	ip link add "${interface}" type wireguard
	ip link set "${interface}" mtu "${mtu}"
	ip address add "${address4}/32" peer "${gateways4[i]}" dev "${interface}"
	ip -6 address add "${address6}/128" peer "${gateways6[i]}" dev "${interface}"
	wg set "${interface}" private-key "${key}" peer "${peer}" endpoint "${endpoints[i]}" \
		persistent-keepalive "${keepalive}" allowed-ips 0.0.0.0/0,::/0
	ip link set "${interface}" up
done

candidates="${state}/candidates"
: >"${candidates}"
for i in "${!interfaces[@]}"; do
	rtt=$(ping -n -c 1 -W 3 -I "${interfaces[i]}" "${gateways4[i]}" 2>/dev/null | sed -n 's/.*time=\([0-9.]*\).*/\1/p' || true)
	handshake=$(wg show "${interfaces[i]}" latest-handshakes | awk '{print $2}')
	[[ "${handshake:-0}" -gt 0 ]] && printf '%s\t%s\n' "${rtt:-999999}" "$i" >>"${candidates}"
done
[[ -s "${candidates}" ]] || {
	echo "no Parker concentrator completed a WireGuard handshake" >&2
	exit 1
}
selected=""
for i in "${!interfaces[@]}"; do
	[[ "${interfaces[i]}" == "wg_c${FF_CONCENTRATOR:-}" ]] && grep -q $'\t'"${i}"'$' "${candidates}" && selected=$i
done
selected=${selected:-$(sort -n "${candidates}" | head -n 1 | cut -f2)}
interface=${interfaces[selected]}
ip route flush default
ip -6 route flush default
ip route add default dev "${interface}"
ip -6 route add default dev "${interface}"
printf '%s\n' "${interface}" >"${state}/selected"
{
	for dns in ${FF_DNS_SERVERS}; do echo "nameserver ${dns}"; done
} >"${state}/resolv.conf"

touch /run/ff-egress-ready
trap 'kill "${sleep_pid:-}" 2>/dev/null; exit 0' TERM INT
while true; do
	sleep 15 & sleep_pid=$!
	wait "${sleep_pid}"
	handshake=$(wg show "${interface}" latest-handshakes | awk '{print $2}')
	(( $(date +%s) - ${handshake:-0} < 180 )) && continue
	for i in "${!interfaces[@]}"; do
		handshake=$(wg show "${interfaces[i]}" latest-handshakes | awk '{print $2}')
		if (( $(date +%s) - ${handshake:-0} < 180 )); then
			interface=${interfaces[i]}
			ip route replace default dev "${interface}"
			ip -6 route replace default dev "${interface}"
			printf '%s\n' "${interface}" >"${state}/selected"
			break
		fi
	done
done
