#!/usr/bin/bash
# Setup a TPM-backed SSH key via tpm2-pkcs11
set -euo pipefail

export PYTHON_INTERPRETER=/usr/bin/python3

LABEL="${1:-ssh}"
ALGORITHM="${2:-ecc256}"

echo "=== TPM-backed SSH key setup ==="
echo "Label: $LABEL"
echo "Algorithm: $ALGORITHM"
echo

# Check prerequisites
if ! command -v tpm2_ptool &>/dev/null; then
    echo "Error: tpm2-pkcs11-tools not installed" >&2
    echo "Run: sudo dnf install tpm2-pkcs11 tpm2-pkcs11-tools" >&2
    exit 1
fi

if ! test -r /dev/tpmrm0; then
    echo "Cannot access /dev/tpmrm0 — setting up udev rule..." >&2
    UDEV_RULE='KERNEL=="tpmrm[0-9]*", MODE="0660", GROUP="wheel"'
    UDEV_FILE="/etc/udev/rules.d/99-tpm.rules"
    sudo bash -c "echo '$UDEV_RULE' > $UDEV_FILE"
    sudo udevadm control --reload-rules
    sudo udevadm trigger /dev/tpmrm0
    if ! test -r /dev/tpmrm0; then
        echo "Error: Still cannot access /dev/tpmrm0 after udev rule. Check group membership." >&2
        exit 1
    fi
    echo "udev rule installed — /dev/tpmrm0 is now accessible."
fi

# Read PINs
read -rsp "SO PIN (admin): " SOPIN
echo
read -rsp "User PIN: " USERPIN
echo

echo
echo "Initializing store..."
INIT_OUTPUT=$(tpm2_ptool init 2>&1)
PID=$(echo "$INIT_OUTPUT" | grep -oP '(?<=id: )\d+' | tail -1)
if [[ -z "$PID" ]]; then
    echo "Error: Could not determine primary object ID from init output:" >&2
    echo "$INIT_OUTPUT" >&2
    exit 1
fi
echo "$INIT_OUTPUT"

echo "Adding token (pid=$PID, label=$LABEL)..."
tpm2_ptool addtoken --pid="$PID" --label="$LABEL" \
    --sopin="$SOPIN" --userpin="$USERPIN"

echo "Generating $ALGORITHM key..."
tpm2_ptool addkey --label="$LABEL" --userpin="$USERPIN" \
    --algorithm="$ALGORITHM"

# Clear PINs from memory
SOPIN="" USERPIN=""
unset SOPIN USERPIN

# Find PKCS#11 module
PKCS11_MODULE=""
for p in /usr/lib64/pkcs11/libtpm2_pkcs11.so /usr/lib/pkcs11/libtpm2_pkcs11.so; do
    if [[ -f "$p" ]]; then
        PKCS11_MODULE="$p"
        break
    fi
done

if [[ -z "$PKCS11_MODULE" ]]; then
    echo "Warning: Could not find libtpm2_pkcs11.so" >&2
    echo "Locate it with: find /usr -name 'libtpm2_pkcs11.so'" >&2
else
    echo
    echo "=== Setup complete ==="
    echo
    echo "Your public key:"
    ssh-keygen -D "$PKCS11_MODULE" 2>/dev/null || echo "(could not extract — try after adding to agent)"
    echo
    echo "To add to ssh-agent:"
    echo "  ssh-add -s $PKCS11_MODULE"
    echo
    echo "To make permanent, add to ~/.ssh/config:"
    echo "  PKCS11Provider $PKCS11_MODULE"
fi
