#!/usr/bin/env bash
set -euo pipefail

if [[ ! -e /dev/tpmrm0 ]]; then
    echo 'No TPM 2.0 resource manager found at /dev/tpmrm0. Enable TPM/fTPM/PTT in firmware (or expose a TPM to the VM), then retry.' >&2
    exit 1
fi
for tool in ssh-tpm-keygen ssh-tpm-agent; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "$tool is missing. Run: brew install elohmeier/tap/ssh-tpm-agent; chezmoi apply; djust setup-tpm-ssh" >&2
        exit 1
    fi
done
if [[ ! -r /dev/tpmrm0 || ! -w /dev/tpmrm0 ]]; then
    echo 'TPM access denied: /dev/tpmrm0 must be readable and writable.' >&2
    echo 'Run: djust setup-tpm-udev (requests polkit authorization), then djust setup-tpm-ssh.' >&2
    exit 1
fi
if ! systemctl --user cat ssh-tpm-agent.service ssh-tpm-agent.socket >/dev/null 2>&1; then
    echo 'TPM user units are unavailable. Run chezmoi apply in a systemd user login session, then retry.' >&2
    exit 1
fi

umask 077
mkdir -p "$HOME/.ssh"
key=$HOME/.ssh/id_ecdsa
if [[ -f $key.tpm ]]; then
    echo "Reusing $key.tpm"
else
    if [[ -e $key || -e $key.pub ]]; then
        echo "Existing SSH key at $key or $key.pub. Move it aside before retrying; TPM setup uses these filenames." >&2
        exit 1
    fi
    echo 'Creating a TPM-bound SSH key. Choose a passphrase when prompted; the key works only on this TPM.'
    ssh-tpm-keygen -f "$key" -C "$(hostname) TPM"
fi
[[ -f $key.pub ]] || ssh-tpm-keygen --print-pubkey "$key.tpm" >"$key.pub"
if ! { systemctl --user daemon-reload &&
    systemctl --user enable --now ssh-tpm-agent.socket &&
    systemctl --user restart ssh-tpm-agent.service; }; then
    echo 'TPM agent failed. Inspect: journalctl --user -b -u ssh-tpm-agent.service' >&2
    exit 1
fi
echo "TPM SSH key ready: $key.tpm"
echo 'Open a new terminal and run ssh-add -l to check the agent. Over SSH, a forwarded agent is preserved.'
cat "$key.pub"
echo 'You can register this public key at https://github.com/settings/ssh/new'
read -rp 'Add this key to GitHub with gh? [y/N] ' answer || exit 0
[[ $answer == [yY]* ]] || exit 0
if ! command -v gh >/dev/null 2>&1; then
    echo 'Install GitHub CLI (brew install gh), run gh auth login, then retry; or use the URL above.' >&2
    exit 1
fi
if ! gh auth status -h github.com >/dev/null 2>&1; then
    echo 'Sign in first: gh auth login -h github.com; then rerun djust setup-tpm-ssh.' >&2
    exit 1
fi
gh api -i user | grep -iE '^x-oauth-scopes:.*(admin|write):public_key' >/dev/null ||
    gh auth refresh -h github.com -s admin:public_key
gh api user/keys --jq '.[].key' | grep -qF "$(cut -d' ' -f2 "$key.pub")" ||
    gh ssh-key add "$key.pub" -t "$(hostname) TPM"
