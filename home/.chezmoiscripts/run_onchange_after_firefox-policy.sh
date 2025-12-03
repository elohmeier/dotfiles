#!/bin/bash
# Install Firefox policy file
# hash: {{ include "dot_config/firefox/policies.json" | sha256sum }}

set -euo pipefail

POLICY_FILE="$HOME/.config/firefox/policies.json"

case "$(uname -s)" in
Darwin)
    if [ -d "$HOME/Applications/Firefox.app" ]; then
        DISTRIBUTION_DIR="$HOME/Applications/Firefox.app/Contents/Resources/distribution"
    elif [ -d "/Applications/Firefox.app" ]; then
        DISTRIBUTION_DIR="/Applications/Firefox.app/Contents/Resources/distribution"
        NEEDS_SUDO=1
    fi
    ;;
Linux)
    # Flatpak Firefox uses extension point
    if flatpak list 2>/dev/null | grep -q org.mozilla.firefox; then
        DISTRIBUTION_DIR="$HOME/.local/share/flatpak/extension/org.mozilla.firefox.systemconfig/x86_64/stable/policies"
    fi
    ;;
esac

if [ -z "${DISTRIBUTION_DIR:-}" ]; then
    exit 0
fi

mkdir -p "$DISTRIBUTION_DIR"
if [ "${NEEDS_SUDO:-}" = 1 ]; then
    sudo cp "$POLICY_FILE" "$DISTRIBUTION_DIR/policies.json"
else
    cp "$POLICY_FILE" "$DISTRIBUTION_DIR/policies.json"
fi
