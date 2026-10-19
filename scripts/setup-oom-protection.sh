#!/usr/bin/env bash
# Keep remote access (tailscaled, sshd) alive under memory pressure.
#
# - MGLRU min_ttl_ms: OOM-kill instead of thrashing for minutes
# - memory.min + OOMScoreAdjust for system.slice, tailscaled and sshd
# - cap user sessions and let systemd-oomd act on pressure and swap
#
# Idempotent: safe to re-run.

set -euo pipefail

[[ $EUID -eq 0 ]] || exec sudo "$0" "$@"

put() { install -Dm644 /dev/stdin "$1"; }

put /etc/tmpfiles.d/mglru-min-ttl.conf <<'EOF'
w /sys/kernel/mm/lru_gen/min_ttl_ms - - - - 1000
EOF

put /etc/systemd/system/system.slice.d/50-oom-protect.conf <<'EOF'
[Slice]
MemoryMin=1G
EOF

put /etc/systemd/system/tailscaled.service.d/50-oom-protect.conf <<'EOF'
[Service]
OOMScoreAdjust=-1000
MemoryMin=256M
EOF

put /etc/systemd/system/sshd.service.d/50-oom-protect.conf <<'EOF'
[Service]
OOMScoreAdjust=-1000
MemoryMin=64M
EOF

put /etc/systemd/system/user@.service.d/50-oom-limits.conf <<'EOF'
[Service]
MemoryHigh=85%
MemoryMax=92%
ManagedOOMMemoryPressure=kill
ManagedOOMMemoryPressureLimit=50%
EOF

put /etc/systemd/system/-.slice.d/50-oomd-swap.conf <<'EOF'
[Slice]
ManagedOOMSwap=kill
EOF

systemd-tmpfiles --create /etc/tmpfiles.d/mglru-min-ttl.conf
systemctl daemon-reload
systemctl restart systemd-oomd
# Apply OOMScoreAdjust without restarting the remote access daemons.
for unit in tailscaled sshd; do
	pid=$(systemctl show -P MainPID "$unit")
	[[ $pid -gt 0 ]] && echo -1000 >"/proc/$pid/oom_score_adj"
done
oomctl
