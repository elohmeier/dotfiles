#!/bin/bash

set -eufo pipefail

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "Not running on macOS. Skipping macOS defaults configuration."
    exit 0
fi

# defaults write -g AppleEnableSwipeNavigateWithScrolls -int 0
# defaults write -g AppleMiniaturizeOnDoubleClick -int 0
# defaults write -g ApplePressAndHoldEnabled -int 0
# defaults write -g AppleShowAllExtensions -int 1
# defaults write -g CGDisableCursorLocationMagnification -int 0
# defaults write -g InitialKeyRepeat -int 15
# defaults write -g KeyRepeat -int 2
# defaults write -g NSAutomaticCapitalizationEnabled -int 0
# defaults write -g NSAutomaticDashSubstitutionEnabled -int 0
# defaults write -g NSAutomaticInlinePredictionEnabled -int 0
# defaults write -g NSAutomaticPeriodSubstitutionEnabled -int 0
# defaults write -g NSAutomaticQuoteSubstitutionEnabled -int 0
# defaults write -g NSAutomaticSpellingCorrectionEnabled -int 0
# defaults write -g NSAutomaticTextCorrectionEnabled -int 0
# defaults write -g NSDocumentSaveNewDocumentsToCloud -int 0
# defaults write -g NSUserDictionaryReplacementItems '()'
# defaults write -g WebAutomaticSpellingCorrectionEnabled -int 0
#
# defaults write -g com.apple.keyboard.fnState -int 1
# defaults write -g com.apple.swipescrolldirection -int 0
# defaults write -g com.apple.trackpad.forceClick -int 0

defaults write NSGlobalDomain InitialKeyRepeat -int 15
defaults write NSGlobalDomain KeyRepeat -int 1

defaults write com.microsoft.VSCode ApplePressAndHoldEnabled -bool false

#
# defaults write com.apple.dock autohide -int 1
# defaults write com.apple.dock orientation -string left
defaults write com.apple.dock show-recents -bool false
# defaults write com.apple.dock showDesktopGestureEnabled -int 0
# defaults write com.apple.dock showLaunchpadGestureEnabled -int 0
# defaults write com.apple.dock showMissionControlGestureEnabled -int 0
#
# defaults write com.apple.finder _FXShowPosixPathInTitle -int 1
# defaults write com.apple.finder FXEnableExtensionChangeWarning -int 0

defaults write com.apple.finder ShowPathbar -bool true
defaults write com.apple.finder ShowStatusBar -bool true
defaults write com.apple.finder AppleShowAllExtensions -bool true
defaults write com.apple.finder FXDefaultSearchScope -string SCcf
defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false
defaults write com.apple.finder FXPreferredViewStyle -string Nlsv
defaults write com.apple.finder FXRemoveOldTrashItems -bool true
defaults write com.apple.finder _FXSortFoldersFirst -bool true

defaults write com.apple.loginwindow TALLogoutSavesState -bool false
defaults write com.apple.loginwindow LoginwindowLaunchesRelaunchApps -bool false

# run these to apply immediatly
# killall Finder
# killall Dock
