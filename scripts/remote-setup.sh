#!/bin/sh
# Applies dotfiles uploaded by `djust push-remote` on an offline host
set -ex
export PATH="$HOME/.local/bin:$PATH"
chezmoi init --promptDefaults
chezmoi apply --exclude=scripts ~/.config/fish ~/.config/k9s ~/.local/share/terminfo ~/.tmux.conf
tic -x -o ~/.terminfo ~/.local/share/terminfo/xterm-ghostty.terminfo
chezmoi execute-template <~/.local/share/chezmoi/home/.chezmoiscripts/run_after_configure-fish.sh.tmpl | sh
grep -qs local/bin/fish ~/.bash_profile || echo '[ -t 0 ] && exec ~/.local/bin/fish -l' >>~/.bash_profile
