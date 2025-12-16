#!/bin/bash

set -eufo pipefail

# Check if running on macOS
[[ "$(uname)" == "Darwin" ]] || exit 0

# Create symlinks for application configs on macOS
# Some apps look in Library/Application Support by default on macOS
# but we want to keep configs in .config for consistency

# Define applications that need symlinks
APPS=(
    "k9s"
    "lazygit"
    "process-compose"
    "turborepo"
)

# Define applications in Library/Preferences that need symlinks
PREFS_APPS=(
    "nextjs-nodejs"
)

for app_name in "${APPS[@]}"; do
    MACOS_DIR="$HOME/Library/Application Support/$app_name"
    CONFIG_DIR="$HOME/.config/$app_name"

    # Skip if config directory doesn't exist
    if [[ ! -d "$CONFIG_DIR" ]]; then
        echo "Skipping $app_name: $CONFIG_DIR doesn't exist"
        continue
    fi

    # Check if correct symlink already exists
    if [[ -L "$MACOS_DIR" && "$(readlink "$MACOS_DIR")" == "$CONFIG_DIR" ]]; then
        echo "Symlink already correct: $MACOS_DIR -> $CONFIG_DIR"
        continue
    fi

    # Handle existing directory/symlink by moving to backup
    if [[ -e "$MACOS_DIR" ]]; then
        BACKUP_DIR="${MACOS_DIR}.backup"

        # Abort if backup already exists
        if [[ -e "$BACKUP_DIR" ]]; then
            echo "ERROR: Backup already exists: $BACKUP_DIR"
            echo "Please remove or rename the backup before running this script."
            exit 1
        fi

        # Move existing to backup
        mv "$MACOS_DIR" "$BACKUP_DIR"
        echo "WARNING: Moved existing $MACOS_DIR to $BACKUP_DIR"
    fi

    # Create the parent directory if it doesn't exist
    mkdir -p "$(dirname "$MACOS_DIR")"

    # Create symlink
    ln -sf "$CONFIG_DIR" "$MACOS_DIR"

    echo "Created symlink: $MACOS_DIR -> $CONFIG_DIR"
done

# Handle Library/Preferences apps
for app_name in "${PREFS_APPS[@]}"; do
    MACOS_DIR="$HOME/Library/Preferences/$app_name"
    CONFIG_DIR="$HOME/.config/$app_name"

    # Skip if config directory doesn't exist
    if [[ ! -d "$CONFIG_DIR" ]]; then
        echo "Skipping $app_name: $CONFIG_DIR doesn't exist"
        continue
    fi

    # Check if correct symlink already exists
    if [[ -L "$MACOS_DIR" && "$(readlink "$MACOS_DIR")" == "$CONFIG_DIR" ]]; then
        echo "Symlink already correct: $MACOS_DIR -> $CONFIG_DIR"
        continue
    fi

    # Handle existing directory/symlink by moving to backup
    if [[ -e "$MACOS_DIR" ]]; then
        BACKUP_DIR="${MACOS_DIR}.backup"

        # Abort if backup already exists
        if [[ -e "$BACKUP_DIR" ]]; then
            echo "ERROR: Backup already exists: $BACKUP_DIR"
            echo "Please remove or rename the backup before running this script."
            exit 1
        fi

        # Move existing to backup
        mv "$MACOS_DIR" "$BACKUP_DIR"
        echo "WARNING: Moved existing $MACOS_DIR to $BACKUP_DIR"
    fi

    # Create the parent directory if it doesn't exist
    mkdir -p "$(dirname "$MACOS_DIR")"

    # Create symlink
    ln -sf "$CONFIG_DIR" "$MACOS_DIR"

    echo "Created symlink: $MACOS_DIR -> $CONFIG_DIR"
done
