#!/bin/bash
# Install Firefox policy file to the correct location on macOS
# hash: {{ include "dot_config/firefox/policies.json" | sha256sum }}

set -euo pipefail

POLICY_FILE="$HOME/.config/firefox/policies.json"

# Check for Firefox in user Applications first, then system Applications
if [ -d "$HOME/Applications/Firefox.app" ]; then
    FIREFOX_APP="$HOME/Applications/Firefox.app"
    echo "Found Firefox in user Applications"
elif [ -d "/Applications/Firefox.app" ]; then
    FIREFOX_APP="/Applications/Firefox.app"
    echo "Found Firefox in system Applications"
else
    echo "Firefox is not installed, skipping policy installation"
    exit 0
fi

DISTRIBUTION_DIR="$FIREFOX_APP/Contents/Resources/distribution"

# Create distribution directory if it doesn't exist
if [ ! -d "$DISTRIBUTION_DIR" ]; then
    echo "Creating Firefox distribution directory..."
    # Use sudo only for system-wide installation
    if [[ "$FIREFOX_APP" == "/Applications/"* ]]; then
        sudo mkdir -p "$DISTRIBUTION_DIR"
    else
        mkdir -p "$DISTRIBUTION_DIR"
    fi
fi

# Copy the policy file
echo "Installing Firefox policy file..."
if [[ "$FIREFOX_APP" == "/Applications/"* ]]; then
    sudo cp "$POLICY_FILE" "$DISTRIBUTION_DIR/policies.json"
    sudo chmod 644 "$DISTRIBUTION_DIR/policies.json"
else
    cp "$POLICY_FILE" "$DISTRIBUTION_DIR/policies.json"
    chmod 644 "$DISTRIBUTION_DIR/policies.json"
fi

echo "Firefox policy installed successfully at $DISTRIBUTION_DIR/policies.json"
echo "Please restart Firefox for the policy to take effect."