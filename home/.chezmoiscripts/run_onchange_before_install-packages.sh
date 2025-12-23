#!/bin/bash

set -uo pipefail

if ! command -v brew &>/dev/null; then
    exit 0
fi

BREWS=(
    bat
    btop
    eza
    fd
    fish
    fzf
    just
    ncdu
    sops
    uv
    vivid
    zoxide
)

echo "Installing packages..."

for brew in "${BREWS[@]}"; do
    echo "brew \"$brew\""
done | brew bundle --file=/dev/stdin || true
