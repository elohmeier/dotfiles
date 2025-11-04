#!/bin/bash
set -euo pipefail

# Install xdg-utils for WSL using apt
if command -v apt-get &>/dev/null; then
    sudo apt-get update
    sudo apt-get install -y desktop-file-utils xdg-utils
else
    echo "apt-get not found. Skipping xdg-utils installation."
    exit 0
fi
