#!/usr/bin/env bash
# Configure automatic /home snapshots on Fedora Atomic / Bluefin.
#
# Defaults to 30 daily read-only snapshots. Override at setup time with:
#   SNAPSHOT_CALENDAR=hourly SNAPSHOT_KEEP=48 ./setup-btrfs-home-snapshots.sh

set -euo pipefail

[[ $EUID -ne 0 ]] || {
	echo "Run as your normal user; the script uses sudo as needed." >&2
	exit 1
}

keep=${SNAPSHOT_KEEP:-30}
calendar=${SNAPSHOT_CALENDAR:-daily}
source=$(realpath /home)
directory=$source/.snapshots

[[ $keep =~ ^[1-9][0-9]*$ ]]
[[ $(findmnt -no FSTYPE -T "$source") == btrfs ]]
systemd-analyze calendar "$calendar" >/dev/null
sudo btrfs subvolume show "$source" >/dev/null

if [[ -e $directory ]]; then
	sudo btrfs subvolume show "$directory" >/dev/null
else
	sudo btrfs subvolume create "$directory"
fi
sudo chmod 700 "$directory"
sudo restorecon "$directory"

sudo install -Dm755 /dev/stdin /usr/local/sbin/btrfs-home-snapshot <<'EOF'
#!/usr/bin/bash
set -euo pipefail

source=$(realpath /home)
directory=$source/.snapshots
keep=${SNAPSHOT_KEEP:-30}
snapshot=$directory/home-$(date --utc +%Y%m%dT%H%M%SZ)

[[ $keep =~ ^[1-9][0-9]*$ ]]
btrfs subvolume snapshot -r "$source" "$snapshot"

mapfile -t snapshots < <(
	find "$directory" -mindepth 1 -maxdepth 1 -type d \
		-regextype posix-extended -regex '.*/home-[0-9]{8}T[0-9]{6}Z' | sort -r
)
for old in "${snapshots[@]:keep}"; do
	btrfs subvolume show "$old" >/dev/null
	btrfs subvolume delete "$old"
done
EOF

sudo install -Dm644 /dev/stdin /etc/systemd/system/btrfs-home-snapshot.service <<EOF
[Unit]
Description=Create a read-only Btrfs snapshot of /home
RequiresMountsFor=/home

[Service]
Type=oneshot
Environment=SNAPSHOT_KEEP=$keep
ExecStart=/usr/local/sbin/btrfs-home-snapshot
Nice=19
IOSchedulingClass=idle
EOF

sudo install -Dm644 /dev/stdin /etc/systemd/system/btrfs-home-snapshot.timer <<EOF
[Unit]
Description=Create periodic Btrfs snapshots of /home

[Timer]
OnCalendar=$calendar
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now btrfs-home-snapshot.timer
sudo systemctl start btrfs-home-snapshot.service

echo "Keeping the latest $keep /home snapshots on the '$calendar' schedule."
sudo btrfs subvolume list -ro "$directory"
