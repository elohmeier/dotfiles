#!/usr/bin/env bash
# Set up hibernation on Fedora Atomic / Bluefin (rpm-ostree + btrfs + LUKS).
#
# Creates a btrfs swapfile sized for hibernation, registers it in fstab,
# disables zram, configures kernel resume= args via rpm-ostree, and applies
# SELinux labels so logind can traverse the swap directory.
#
# Idempotent: safe to re-run. Does not reboot — prints instructions instead.
#
# Overrides:
#   SWAP_DIR=/var/swap        Directory (subvolume) holding the swapfile
#   SWAP_FILE=swapfile        Filename inside SWAP_DIR
#   SWAP_SIZE_GIB=<n>         Override default size (RAM + 4 GiB)

set -euo pipefail

SWAP_DIR="${SWAP_DIR:-/var/swap}"
SWAP_FILE="${SWAP_FILE:-swapfile}"
SWAP_PATH="${SWAP_DIR}/${SWAP_FILE}"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m'

info() { echo "${BLUE}[INFO]${NC} $*"; }
ok() { echo "${GREEN}[ OK ]${NC} $*"; }
warn() { echo "${YELLOW}[WARN]${NC} $*" >&2; }
die() {
	echo "${RED}[FAIL]${NC} $*" >&2
	exit 1
}

require() {
	command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

main() {
	[[ $EUID -eq 0 ]] && die "run as your normal user; the script uses sudo as needed"
	[[ "$(uname -s)" == "Linux" ]] || die "Linux only"

	for cmd in rpm-ostree btrfs swapon systemctl semanage restorecon findmnt awk; do
		require "$cmd"
	done

	info "Pre-flight checks..."
	preflight_checks

	info "Computing swap size..."
	local swap_gib
	swap_gib="$(compute_swap_size)"
	info "Will use ${swap_gib} GiB swap (RAM=$(ram_gib) GiB, image_size=$(image_size_mib) MiB)"

	info "Step 1/6: Creating swap subvolume and file at ${SWAP_PATH}..."
	create_swapfile "$swap_gib"

	info "Step 2/6: Applying SELinux label (swapfile_t)..."
	apply_selinux_label

	info "Step 3/6: Enabling swap and registering in /etc/fstab..."
	enable_swap

	info "Step 4/6: Disabling zram so hibernation uses the disk swap..."
	disable_zram

	info "Step 5/6: Configuring kernel resume= args via rpm-ostree..."
	configure_kargs

	info "Step 6/6: Verifying configuration..."
	verify_config

	cat <<EOF

${GREEN}Setup staged successfully.${NC}

Next steps:
  1. ${YELLOW}Reboot${NC} so the new kernel args take effect:
       sudo systemctl reboot
  2. After reboot, verify:
       cat /proc/cmdline    # should contain resume= and resume_offset=
       swapon --show        # should show ${SWAP_PATH}, no zram
  3. Test hibernation:
       sudo systemctl hibernate

If hibernate still fails with SELinux denials after reboot, collect them
and build a local policy module:
  sudo ausearch -m AVC,USER_AVC -ts recent \\
    | grep -E 'systemd_(logind|sleep|hibernate)' \\
    | audit2allow -M systemd_hibernate_local
  sudo semodule -i systemd_hibernate_local.pp

EOF
}

preflight_checks() {
	local root_fstype
	root_fstype="$(findmnt -no FSTYPE /var)"
	[[ "$root_fstype" == "btrfs" ]] || die "/var must be btrfs (got: $root_fstype)"

	rpm-ostree --version >/dev/null 2>&1 || die "rpm-ostree not functional"

	if ! btrfs filesystem mkswapfile --help >/dev/null 2>&1; then
		die "btrfs-progs too old; need 'btrfs filesystem mkswapfile' (>=5.14)"
	fi
}

ram_gib() {
	awk '/^MemTotal:/ { printf "%d", ($2 + 1048575) / 1048576 }' /proc/meminfo
}

image_size_mib() {
	if [[ -r /sys/power/image_size ]]; then
		awk '{ printf "%d", $1 / 1048576 }' /sys/power/image_size
	else
		echo "unknown"
	fi
}

compute_swap_size() {
	if [[ -n "${SWAP_SIZE_GIB:-}" ]]; then
		echo "$SWAP_SIZE_GIB"
		return
	fi
	# RAM + 4 GiB headroom, covers compressed image + slack.
	echo $(($(ram_gib) + 4))
}

create_swapfile() {
	local size_gib="$1"

	if [[ -f "$SWAP_PATH" ]]; then
		ok "swapfile already exists at ${SWAP_PATH}, skipping creation"
		return
	fi

	if ! sudo btrfs subvolume show "$SWAP_DIR" >/dev/null 2>&1; then
		sudo btrfs subvolume create "$SWAP_DIR"
		ok "created subvolume ${SWAP_DIR}"
	else
		ok "subvolume ${SWAP_DIR} already exists"
	fi

	sudo chattr +C "$SWAP_DIR" 2>/dev/null || true
	sudo btrfs filesystem mkswapfile --size "${size_gib}g" "$SWAP_PATH"
	ok "created ${size_gib} GiB swapfile"
}

apply_selinux_label() {
	if [[ "$(getenforce 2>/dev/null || echo Disabled)" == "Disabled" ]]; then
		warn "SELinux is disabled; skipping label step"
		return
	fi

	local fcontext_pat="${SWAP_DIR}(/.*)?"
	if ! sudo semanage fcontext -l 2>/dev/null | grep -qF "$fcontext_pat"; then
		sudo semanage fcontext -a -t swapfile_t "$fcontext_pat"
		ok "registered fcontext: ${fcontext_pat} -> swapfile_t"
	else
		ok "fcontext for ${SWAP_DIR} already registered"
	fi
	sudo restorecon -RFv "$SWAP_DIR" >/dev/null
	ok "relabeled ${SWAP_DIR}"
}

enable_swap() {
	if ! swapon --show=NAME --noheadings | grep -qx "$SWAP_PATH"; then
		sudo swapon "$SWAP_PATH"
		ok "activated ${SWAP_PATH}"
	else
		ok "${SWAP_PATH} already active"
	fi

	local fstab_line="${SWAP_PATH} none swap defaults 0 0"
	if ! grep -qF "$SWAP_PATH" /etc/fstab; then
		echo "$fstab_line" | sudo tee -a /etc/fstab >/dev/null
		ok "added fstab entry"
	else
		ok "fstab entry already present"
	fi
}

disable_zram() {
	local conf=/etc/systemd/zram-generator.conf
	if [[ -f "$conf" ]] && ! grep -qE '^[[:space:]]*[^#[:space:]]' "$conf"; then
		ok "zram already disabled via ${conf}"
		return
	fi
	echo '# zram disabled to allow hibernation (managed by setup-hibernation.sh)' |
		sudo tee "$conf" >/dev/null
	ok "wrote empty override to ${conf} (takes effect at next boot)"
}

configure_kargs() {
	local uuid offset current
	uuid="$(findmnt -no UUID /var)"
	[[ -n "$uuid" ]] || die "could not determine /var filesystem UUID"

	offset="$(sudo btrfs inspect-internal map-swapfile -r "$SWAP_PATH")"
	[[ "$offset" =~ ^[0-9]+$ ]] || die "unexpected map-swapfile output: $offset"

	current="$(rpm-ostree kargs)"
	local want_resume="resume=UUID=${uuid}"
	local want_offset="resume_offset=${offset}"

	local args=()
	if ! grep -qw "$want_resume" <<<"$current"; then
		args+=(--append="$want_resume")
	fi
	if ! grep -qw "$want_offset" <<<"$current"; then
		# strip any stale resume_offset before adding the new one
		local stale
		stale="$(grep -oE 'resume_offset=[0-9]+' <<<"$current" | grep -v "^${want_offset}$" || true)"
		if [[ -n "$stale" ]]; then
			args+=(--delete="$stale")
		fi
		args+=(--append="$want_offset")
	fi

	if [[ ${#args[@]} -eq 0 ]]; then
		ok "kargs already contain ${want_resume} and ${want_offset}"
		return
	fi

	wait_for_rpm_ostree
	sudo rpm-ostree kargs "${args[@]}"
	ok "updated kargs: ${args[*]}"
}

wait_for_rpm_ostree() {
	# Bluefin runs uupd / rpm-ostreed-automatic, which can hold the transaction
	# lock. Pause them, cancel any in-flight tx, then let the caller proceed.
	# Caller is expected to leave them as-is on exit (re-enabled at boot).
	for unit in uupd.service uupd.timer rpm-ostreed-automatic.timer; do
		if systemctl is-active --quiet "$unit"; then
			sudo systemctl stop "$unit" || true
		fi
	done
	sudo rpm-ostree cancel >/dev/null 2>&1 || true
}

verify_config() {
	swapon --show=NAME,SIZE,TYPE --noheadings | sed 's/^/  /'
	echo "  staged kargs:"
	rpm-ostree kargs | tr ' ' '\n' | grep -E '^resume' | sed 's/^/    /' || true
}

main "$@"
