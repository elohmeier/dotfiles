#!/bin/bash
# Refreshes static tools and the chezmoi source from GitHub mirror $1 at ref $2 (chezmoi update.command on hosts without GitHub access)
set -euo pipefail
rel() { curl -fsSL "$1/$2/releases/download/$3"; }
v="chezmoi-2.73.2 fish-4.9.3 fzf-0.74.5 k9s-0.51.0 tmux-3.7b"
cd "$(mktemp -d)"
if [ "$(cat ~/.local/bin/.bundle 2>/dev/null)" != "$v" ]; then
    rel "$1" twpayne/chezmoi v2.73.2/chezmoi-linux-amd64-musl >chezmoi
    rel "$1" fish-shell/fish-shell 4.9.3/fish-4.9.3-linux-x86_64.tar.xz | tar -xJ
    rel "$1" junegunn/fzf v0.74.5/fzf-0.74.5-linux_amd64.tar.gz | tar -xz
    rel "$1" derailed/k9s v0.51.0/k9s_Linux_amd64.tar.gz | tar -xz k9s
    rel "$1" mjakob-gh/build-static-tmux v3.7b/tmux.linux-amd64.stripped.gz | gunzip >tmux
    chmod +x chezmoi fish fzf k9s tmux
    mkdir -p ~/.local/bin && mv -f chezmoi fish fzf k9s tmux ~/.local/bin/
    echo "$v" >~/.local/bin/.bundle
fi
mkdir src && curl -fsSL "$1/elohmeier/dotfiles/archive/${2:-main}.tar.gz" | tar -xz --strip-components=1 -C src
mkdir -p ~/.local/share && rm -rf ~/.local/share/chezmoi && mv src ~/.local/share/chezmoi
