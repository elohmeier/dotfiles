#!/bin/bash
# Installs static tools and applies dotfiles on a host that reaches GitHub only via mirror $1 (see `djust push-remote`)
set -euxo pipefail
rel() { curl -fsSL "$1/$2/releases/download/$3"; }
v="chezmoi-2.73.2 fish-4.9.3 fzf-0.74.5 k9s-0.51.0 tmux-3.7b"
if [ "$(cat ~/.local/bin/.bundle 2>/dev/null)" != "$v" ]; then
    cd "$(mktemp -d)"
    rel "$1" twpayne/chezmoi v2.73.2/chezmoi-linux-amd64-musl >chezmoi
    rel "$1" fish-shell/fish-shell 4.9.3/fish-4.9.3-linux-x86_64.tar.xz | tar -xJ
    rel "$1" junegunn/fzf v0.74.5/fzf-0.74.5-linux_amd64.tar.gz | tar -xz
    rel "$1" derailed/k9s v0.51.0/k9s_Linux_amd64.tar.gz | tar -xz k9s
    rel "$1" mjakob-gh/build-static-tmux v3.7b/tmux.linux-amd64.stripped.gz | gunzip >tmux
    chmod +x chezmoi fish fzf k9s tmux
    mkdir -p ~/.local/bin && mv -f chezmoi fish fzf k9s tmux ~/.local/bin/
    echo "$v" >~/.local/bin/.bundle
fi
export PATH="$HOME/.local/bin:$PATH"
chezmoi init --promptDefaults
chezmoi apply --exclude=scripts ~/.config/fish ~/.config/k9s ~/.local/share/terminfo ~/.tmux.conf
tic -x -o ~/.terminfo ~/.local/share/terminfo/xterm-ghostty.terminfo
chezmoi execute-template <~/.local/share/chezmoi/home/.chezmoiscripts/run_after_configure-fish.sh.tmpl | sh
grep -qs local/bin/fish ~/.bash_profile || echo '[ -t 0 ] && exec ~/.local/bin/fish -l' >>~/.bash_profile
