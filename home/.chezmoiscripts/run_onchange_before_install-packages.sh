#!/bin/sh

set -u

command -v brew >/dev/null || exit 0

echo "Installing packages..."

brew bundle --file=/dev/stdin <<EOF || true
brew "bat"
brew "btop"
brew "eza"
brew "fd"
$(command -v fish >/dev/null || printf 'brew "fish"\n')
brew "fzf"
brew "just"
brew "ncdu"
brew "sops"
brew "uv"
brew "vivid"
brew "zoxide"
EOF
