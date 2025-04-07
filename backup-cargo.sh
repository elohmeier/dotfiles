#!/bin/bash
# Script to backup Cargo packages installed via cargo install

# Create directory for cargo backups if it doesn't exist
mkdir -p cargo-backups

# Get list of installed cargo packages
# cargo install --list shows all installed packages
cargo install --list | grep -E "^[a-zA-Z0-9_-]+ v[0-9]" | awk '{print $1}' > cargo-backups/cargo-packages.txt

echo "Cargo packages backed up to cargo-backups/cargo-packages.txt"
