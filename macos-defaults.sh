#!/bin/bash

# Script to apply macOS default settings
# Based on the provided configuration

echo "Applying macOS default settings..."

# Dock settings
echo "Configuring Dock..."
defaults write com.apple.dock "show-recents" -bool false

# Login window settings
echo "Configuring Login Window..."
defaults write com.apple.loginwindow TALLogoutSavesState -bool false
defaults write com.apple.loginwindow LoginwindowLaunchesRelaunchApps -bool false

# Finder settings
echo "Configuring Finder..."
defaults write com.apple.finder ShowPathbar -bool true
defaults write com.apple.finder ShowStatusBar -bool true
defaults write com.apple.finder AppleShowAllExtensions -bool true
defaults write com.apple.finder FXDefaultSearchScope -string "SCcf"
defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false
defaults write com.apple.finder FXPreferredViewStyle -string "Nlsv"
defaults write com.apple.finder FXRemoveOldTrashItems -bool true
defaults write com.apple.finder _FXSortFoldersFirst -bool true

# Global settings
echo "Configuring global settings..."
defaults write NSGlobalDomain InitialKeyRepeat -int 15
defaults write NSGlobalDomain KeyRepeat -int 1

# Restart affected applications
echo "Restarting affected applications..."
killall Finder
killall Dock

echo "macOS defaults have been applied successfully!"
