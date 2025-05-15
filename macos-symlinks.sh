#!/bin/bash
# Script to set up macOS-specific symlinks for various tools

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Function to create a symlink if it doesn't exist
create_symlink() {
    local source="$1"
    local target="$2"

    # Create the source directory if it doesn't exist
    mkdir -p "$(dirname "$source")"

    # Create the target directory if it doesn't exist
    mkdir -p "$(dirname "$target")"

    # Check if the symlink already exists
    if [ -L "$source" ]; then
        echo -e "${YELLOW}Symlink already exists:${NC} $source -> $(readlink "$source")"
        # Check if it points to the correct target
        if [ "$(readlink "$source")" != "$target" ]; then
            echo -e "${YELLOW}Updating symlink to point to:${NC} $target"
            rm "$source"
            ln -s "$target" "$source"
        fi
    elif [ -e "$source" ]; then
        echo -e "${YELLOW}Warning:${NC} $source exists but is not a symlink. Backing up and creating symlink."
        mv "$source" "$source.backup"
        ln -s "$target" "$source"
    else
        echo -e "${GREEN}Creating symlink:${NC} $source -> $target"
        ln -s "$target" "$source"
    fi
}

# Only run on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "This script is only for macOS systems."
    exit 1
fi

# k9s: Link from ~/Library/Application Support/k9s to ~/.config/k9s
create_symlink "$HOME/Library/Application Support/k9s" "$HOME/.config/k9s"

# process-compose: Link from ~/Library/Application Support/process-compose to ~/.config/process-compose
create_symlink "$HOME/Library/Application Support/process-compose" "$HOME/.config/process-compose"

# aerc: Link from ~/Library/Preferences/aerc to ~/.config/aerc
create_symlink "$HOME/Library/Preferences/aerc" "$HOME/.config/aerc"

# pnpm: Link from ~/Library/Preferences/pnpm/rc to ~/.config/pnpm/rc
create_symlink "$HOME/Library/Preferences/pnpm/rc" "$HOME/.config/pnpm/rc"

# Add more tool symlinks as needed below
# Example:
# create_symlink "$HOME/Library/Application Support/tool-name" "$HOME/.config/tool-name"

# dvc: Link from ~/Library/Application Support/dvc/config to ~/.config/dvc/config
create_symlink "$HOME/Library/Application Support/dvc/config" "$HOME/.config/dvc/config"

echo -e "\n${GREEN}macOS symlinks setup complete!${NC}"
