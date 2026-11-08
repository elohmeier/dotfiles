#!/bin/sh
set -eu

if [ ! -e /dev/tpmrm0 ]; then
    echo 'No TPM 2.0 resource manager found at /dev/tpmrm0. Enable TPM/fTPM/PTT in firmware (or expose a TPM to the VM), then retry.' >&2
    exit 1
fi
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run djust setup-tpm-udev as your normal user; run0 requests administrator authorization through polkit.' >&2
    exit 1
fi
if [ -r /dev/tpmrm0 ] && [ -w /dev/tpmrm0 ]; then
    echo 'TPM device is already readable and writable. Next: djust setup-tpm-ssh'
    exit 0
fi
if ! command -v run0 >/dev/null 2>&1; then
    echo 'run0 is required. Install systemd 256+ and polkit with your distribution package manager, then retry.' >&2
    exit 1
fi

echo "Granting $(id -un) persistent access to /dev/tpmrm0 via /etc/udev/rules.d/99-tpm.rules (owner UID $(id -u), mode 0600)."
echo 'Approve the polkit administrator prompt to install and apply this rule.'
if ! run0 /bin/sh -eu -c '
    mkdir -p /etc/udev/rules.d
    printf "KERNEL==\"tpmrm0\", OWNER=\"%s\", MODE=\"0600\"\n" "$1" > /etc/udev/rules.d/99-tpm.rules
    udevadm control --reload-rules
    udevadm trigger --action=change --settle /dev/tpmrm0
' sh "$(id -u)"; then
    echo 'TPM permission setup failed. Check the error above. For authorization failures, retry in an interactive login session and check: systemctl status polkit.service systemd-udevd.service' >&2
    exit 1
fi
if [ ! -r /dev/tpmrm0 ] || [ ! -w /dev/tpmrm0 ]; then
    echo 'TPM access is still denied. Inspect: ls -l /dev/tpmrm0; journalctl -b -u systemd-udevd.service' >&2
    exit 1
fi
echo 'TPM access is ready; no logout is needed. Next: djust setup-tpm-ssh'
