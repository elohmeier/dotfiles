#!/bin/bash

set -eufo pipefail

# Create symlinks for application configs on macOS
# Some apps look in Library/Application Support by default on macOS
# but we want to keep configs in .config for consistency

create_symlink() {
    local base_dir="$1"
    local app_name="$2"
    local macos_dir="$base_dir/$app_name"
    local config_dir="$HOME/.config/$app_name"

    if [[ ! -d "$config_dir" ]]; then
        echo "Skipping $app_name: $config_dir doesn't exist"
        return
    fi

    if [[ -L "$macos_dir" && "$(readlink "$macos_dir")" == "$config_dir" ]]; then
        echo "Symlink already correct: $macos_dir -> $config_dir"
        return
    fi

    if [[ -e "$macos_dir" ]]; then
        local backup_dir="${macos_dir}.backup"
        if [[ -e "$backup_dir" ]]; then
            echo "ERROR: Backup already exists: $backup_dir"
            exit 1
        fi
        mv "$macos_dir" "$backup_dir"
        echo "WARNING: Moved existing $macos_dir to $backup_dir"
    fi

    mkdir -p "$(dirname "$macos_dir")"
    ln -sf "$config_dir" "$macos_dir"
    echo "Created symlink: $macos_dir -> $config_dir"
}

for app in k9s lazygit process-compose turborepo; do
    create_symlink "$HOME/Library/Application Support" "$app"
done

create_symlink "$HOME/Library/Preferences" "nextjs-nodejs"
