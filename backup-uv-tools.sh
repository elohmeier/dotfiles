#!/bin/bash
# Script to backup Python tools installed via uv tool install

# Create directory for uv tool backups if it doesn't exist
mkdir -p uv-backups

# Get list of installed tools
# uv tool list shows all installed tools
uv tool list | grep -v "^-" | awk '{print $1}' > uv-backups/uv-tools.txt

echo "UV tools backed up to uv-backups/uv-tools.txt"
