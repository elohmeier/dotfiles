#!/bin/bash
# Refreshes static tools and the chezmoi source from GitHub mirror $1 at ref $2 (chezmoi update.command on hosts without GitHub access)
# Tools go to /usr/local/bin (via su, passwordless there) since /home is tiny on those hosts
set -euo pipefail
cd "$(mktemp -d)"
if [ -z "${MIRROR_SRC_DONE:-}" ]; then
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
    # Continue with the freshly fetched script so tool bumps apply in the same update
    MIRROR_SRC_DONE=1 exec bash ~/.local/share/chezmoi/scripts/mirror-update.sh "$1"
fi
b=/usr/local/bin
rel() { curl -fsSL "$1/$2/releases/download/$3"; }
# renovate: datasource=github-releases depName=twpayne/chezmoi
CHEZMOI_V=v2.73.3
# renovate: datasource=github-releases depName=fish-shell/fish-shell
FISH_V=4.9.3
# renovate: datasource=github-releases depName=junegunn/fzf
FZF_V=v0.74.5
# renovate: datasource=github-releases depName=derailed/k9s
K9S_V=v0.51.0
# renovate: datasource=github-releases depName=mjakob-gh/build-static-tmux versioning=loose
TMUX_V=v3.7b
# renovate: datasource=github-releases depName=sxyazi/yazi
YAZI_V=v26.9.1
# renovate: datasource=github-releases depName=mikefarah/yq
YQ_V=v4.54.1
v="chezmoi-$CHEZMOI_V fish-$FISH_V fzf-$FZF_V k9s-$K9S_V tmux-$TMUX_V yazi-$YAZI_V yq-$YQ_V"
if [ "$(cat $b/.dotfiles-bundle 2>/dev/null)" != "$v" ]; then
    rel "$1" twpayne/chezmoi "$CHEZMOI_V/chezmoi-linux-amd64-musl" >chezmoi
    rel "$1" fish-shell/fish-shell "$FISH_V/fish-$FISH_V-linux-x86_64.tar.xz" | tar -xJ
    rel "$1" junegunn/fzf "$FZF_V/fzf-${FZF_V#v}-linux_amd64.tar.gz" | tar -xz
    rel "$1" derailed/k9s "$K9S_V/k9s_Linux_amd64.tar.gz" | tar -xz k9s
    rel "$1" mjakob-gh/build-static-tmux "$TMUX_V/tmux.linux-amd64.stripped.gz" | gunzip >tmux
    rel "$1" sxyazi/yazi "$YAZI_V/yazi-x86_64-unknown-linux-musl.zip" >yazi.zip
    # no unzip on RHEL minimal; platform-python is always there
    "$(command -v python3 || echo /usr/libexec/platform-python)" -m zipfile -e yazi.zip . && mv yazi-*/yazi .
    rel "$1" mikefarah/yq "$YQ_V/yq_linux_amd64" >yq
    echo "$v" >.dotfiles-bundle
    su -c "install -m 755 chezmoi fish fzf k9s tmux yazi yq .dotfiles-bundle $b/"
    rm -f ~/.local/bin/{chezmoi,fish,fzf,k9s,tmux,.bundle}
fi
