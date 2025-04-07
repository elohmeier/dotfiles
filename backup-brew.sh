#!/bin/bash
# Script to backup Homebrew packages and casks

# Create directory for brew backups if it doesn't exist
mkdir -p brew-backups

# Get current date for filename
DATE=$(date +%Y-%m-%d)

# Backup all installed formulae
brew leaves > brew-backups/brew-formulae.txt

# Backup all installed casks
brew list --cask > brew-backups/brew-casks.txt

echo "Brew packages backed up to brew-backups/brew-formulae.txt"
echo "Brew casks backed up to brew-backups/brew-casks.txt"
