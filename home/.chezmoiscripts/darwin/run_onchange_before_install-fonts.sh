#!/bin/bash

set -uo pipefail

if [[ -x /opt/workbrew/bin/brew ]]; then
	brew=/opt/workbrew/bin/brew
else
	brew=$(command -v brew) || exit 0
fi

CASKS=(
	font-ibm-plex-mono
	font-ibm-plex-sans
	font-spleen
)

echo "Installing fonts..."

"$brew" install --cask --fontdir="$HOME/Library/Fonts" "${CASKS[@]}" || true
