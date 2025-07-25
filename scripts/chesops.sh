#!/usr/bin/env bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if sops is installed
if ! command -v sops &> /dev/null; then
    echo "Warning: sops is not installed. Cannot decrypt secrets." >&2
    echo ""
    exit 0
fi

# If an argument is provided, use it as a yaml path with yq
if [ $# -eq 1 ]; then
    sops -d "$SCRIPT_DIR/../secrets.yaml" | yq "$1"
else
    sops -d "$SCRIPT_DIR/../secrets.yaml"
fi
