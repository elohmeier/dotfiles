#!/bin/bash
# Refreshes static tools and the chezmoi source from GitHub mirror $1 at ref $2 (chezmoi update.command on hosts without GitHub access)
# Tools go to /usr/local/bin (via su, passwordless there) since /home is tiny on those hosts
set -euo pipefail
b=/usr/local/bin
rel() { curl -fsSL "$1/$2/releases/download/$3"; }
v="chezmoi-2.73.2 fish-4.9.3 fzf-0.74.5 k9s-0.51.0 tmux-3.7b"
cd "$(mktemp -d)"
if [ "$(cat $b/.dotfiles-bundle 2>/dev/null)" != "$v" ]; then
    rel "$1" twpayne/chezmoi v2.73.2/chezmoi-linux-amd64-musl >chezmoi
    rel "$1" fish-shell/fish-shell 4.9.3/fish-4.9.3-linux-x86_64.tar.xz | tar -xJ
    rel "$1" junegunn/fzf v0.74.5/fzf-0.74.5-linux_amd64.tar.gz | tar -xz
    rel "$1" derailed/k9s v0.51.0/k9s_Linux_amd64.tar.gz | tar -xz k9s
    rel "$1" mjakob-gh/build-static-tmux v3.7b/tmux.linux-amd64.stripped.gz | gunzip >tmux
    echo "$v" >.dotfiles-bundle
    su -c "install -m 755 chezmoi fish fzf k9s tmux .dotfiles-bundle $b/"
    rm -f ~/.local/bin/{chezmoi,fish,fzf,k9s,tmux,.bundle}
fi
# Mirrors cache mutable URLs (branch archives, feeds) by path. GitHub ignores the case of owner/repo,
# so vary it per minute to get a fresh feed, then fetch the immutable archive of its newest commit.
repo=elohmeier/dotfiles n=$(($(date +%s) / 60)) fresh=
for ((i = 0; i < ${#repo}; i++)); do
    c=${repo:i:1}
    ((n >> i & 1)) && c=${c^^}
    fresh+=$c
done
rev="${2:-$(curl -fsSL "$1/$fresh/commits/main.atom" | awk 'match($0, /Commit\/[0-9a-f]+/) && !r { r = substr($0, RSTART + 7, 40) } END { print r }')}"
mkdir src && curl -fsSL "$1/elohmeier/dotfiles/archive/$rev.tar.gz" | tar -xz --strip-components=1 -C src
mkdir -p ~/.local/share && rm -rf ~/.local/share/chezmoi && mv src ~/.local/share/chezmoi
