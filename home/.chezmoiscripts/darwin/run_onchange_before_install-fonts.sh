#!/bin/bash

set -uo pipefail

if ! command -v brew &>/dev/null; then
	exit 0
fi

CASKS=(
	font-ibm-plex-mono
	font-ibm-plex-sans
	font-spleen
)

echo "Installing fonts..."

for cask in "${CASKS[@]}"; do
	echo "cask \"$cask\""
done | brew bundle --file=/dev/stdin || true
