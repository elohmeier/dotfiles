#!/bin/bash

set -euo pipefail

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

font_dir="$HOME/Library/Fonts"
mkdir -p "$font_dir"

if [[ -x /opt/workbrew/bin/brew ]]; then
	# Workbrew's cask installer cannot write to the login user's font directory.
	archive=$(mktemp)
	trap 'unlink "$archive"' EXIT

	for cask in "${CASKS[@]}"; do
		metadata=$("$brew" info --json=v2 --cask "$cask")
		url=$(plutil -extract casks.0.url raw -o - - <<<"$metadata")
		sha=$(plutil -extract casks.0.sha256 raw -o - - <<<"$metadata")
		curl -fsSL "$url" -o "$archive"
		printf '%s  %s\n' "$sha" "$archive" | shasum -a 256 -c - >/dev/null

		while IFS= read -r member; do
			case "$member" in
			*/fonts/complete/otf/*.otf | spleen-*/*.otf)
				tar -xOf "$archive" "$member" >"$font_dir/${member##*/}"
				;;
			esac
		done < <(tar -tf "$archive")
	done
else
	"$brew" install --cask --fontdir="$font_dir" "${CASKS[@]}"
fi
