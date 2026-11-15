#!/usr/bin/env bash
# Install an offline cache migration for the next user-manager startup.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
	exec sudo "$0" "$(id -u)"
fi
user_id=${1:?Usage: setup-btrfs-cache-subvolumes.sh USER_ID}
[[ $user_id =~ ^[0-9]+$ ]]
script_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install -Dm755 "$script_directory/btrfs-cache-subvolumes.sh" /usr/local/sbin/btrfs-cache-subvolumes

install -Dm644 /dev/stdin /etc/systemd/system/btrfs-cache-subvolumes@.service <<'EOF'
[Unit]
Description=Exclude user %i caches from Btrfs home snapshots
RequiresMountsFor=/home
Before=user@%i.service btrfs-home-snapshot.service

[Service]
Type=oneshot
Environment=PATH=/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/usr/local/sbin/btrfs-cache-subvolumes %i
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=2h

[Install]
WantedBy=user@%i.service
EOF

systemctl daemon-reload
systemctl enable "btrfs-cache-subvolumes@$user_id.service"
echo "Cache migration enabled for the next user-manager startup (normally next boot)."
