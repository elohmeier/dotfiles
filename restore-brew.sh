#!/bin/bash
# Script to restore Homebrew packages and casks from backup files

# Check if backup files exist
if [ ! -f brew-backups/brew-formulae.txt ] || [ ! -f brew-backups/brew-casks.txt ]; then
    echo "Error: Backup files not found in brew-backups directory"
    exit 1
fi

# Install Homebrew if not installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Update Homebrew
echo "Updating Homebrew..."
brew update

# Install formulae from backup
echo "Installing formulae from backup..."
xargs brew install < brew-backups/brew-formulae.txt

# Install casks from backup
echo "Installing casks from backup..."
xargs brew install --cask < brew-backups/brew-casks.txt

echo "Brew packages and casks restored successfully!"
