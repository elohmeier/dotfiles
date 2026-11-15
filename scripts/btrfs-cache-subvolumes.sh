#!/usr/bin/env bash
# Run before the user's services start; preserve existing cache contents.
set -euo pipefail

user_id=${1:?Usage: btrfs-cache-subvolumes USER_ID}
[[ $user_id =~ ^[0-9]+$ ]]
home=$(getent passwd "$user_id" | cut -d: -f6)
home=$(realpath -- "$home")
[[ -d $home && $(stat -c %u "$home") == "$user_id" ]]
[[ $(findmnt -no FSTYPE -T "$home") == btrfs ]] || exit 0
if systemctl is-active --quiet "user@$user_id.service"; then
	echo "Run cache migration before user@$user_id.service starts." >&2
	exit 1
fi

convert() {
	local directory=$1 staging=$1.chezmoi-subvolume
	[[ ! -L $directory ]] || return 0
	[[ $(realpath -m -- "$directory") == "$home/"* ]] || return 0
	if [[ -e $staging ]]; then
		echo "Previous migration needs inspection: $staging" >&2
		exit 1
	fi
	if [[ -d $directory && $(stat -c %i "$directory") == 256 ]]; then
		return 0
	fi
	[[ -d $(dirname "$directory") ]] || return 0
	[[ $(findmnt -no FSTYPE -T "$(dirname "$directory")") == btrfs ]] || return 0
	if [[ ! -e $directory ]]; then
		btrfs subvolume create "$directory"
		chown "$user_id:$(stat -c %g "$home")" "$directory"
		return 0
	fi
	btrfs subvolume create "$staging"
	cp -a --reflink=always "$directory/." "$staging/"
	mv --exchange --no-copy --no-target-directory "$directory" "$staging"
	rm -rf -- "$staging"
}

# Whole .cache stays outside snapshots, including caches at nonstandard paths.
for relative in .cache .npm/_cacache .gradle/caches .cargo/registry .cargo/git \
	.local/share/pnpm/store go/pkg/mod; do
	convert "$home/$relative"
done

# ghq workspace roots and Claude worktrees. Cargo's target root is disposable.
for manifest in "$home"/repos/*/*/*/Cargo.toml \
	"$home"/repos/*/*/*/.claude/worktrees/*/Cargo.toml; do
	[[ -f $manifest ]] || continue
	directory=$(dirname "$manifest")/target
	if [[ ! -e $directory || -f $directory/CACHEDIR.TAG ]]; then
		convert "$directory"
	fi
done

directory=$home/repos/github.com/elohmeier/director64/build
[[ ! -d $(dirname "$directory") ]] || convert "$directory"
