#!/usr/bin/env bash
# Configure dialout membership on Fedora Atomic / Bluefin.
#
# On rpm-ostree systems dialout lives in /usr/lib/group, while gpasswd only
# modifies /etc/group. Create a local merge entry before adding the user.
#
# Idempotent: safe to re-run. A logout or reboot is required afterward.

set -euo pipefail

[[ $EUID -eq 0 ]] && { echo "Run as your normal user; the script uses sudo as needed." >&2; exit 1; }

user=$(id -un)
group=$(getent group dialout) || { echo "The dialout group does not exist." >&2; exit 1; }
local_group=$(getent -s files group dialout || true)

if [[ ",${local_group##*:}," == *",${user},"* ]]; then
	echo "${user} is already configured as a dialout member."
	exit 0
fi

if [[ -z $local_group ]]; then
	printf 'dialout:x:%s:\n' "$(cut -d: -f3 <<<"$group")" | sudo tee -a /etc/group >/dev/null
fi

sudo gpasswd --add "$user" dialout
echo "Added ${user} to dialout. Log out and back in, or reboot, to activate it."
