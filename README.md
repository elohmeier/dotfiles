# Dotfiles

Personal dotfiles managed with [chezmoi](https://www.chezmoi.io/).

## Fresh macOS Setup (Recommended)

For a brand new Mac with proper privilege separation:

**Quick setup** (auto-confirms prompts when piped):

```bash
curl -fsSL https://raw.githubusercontent.com/elohmeier/dotfiles/main/scripts/macos-fresh-setup.sh | bash
```

**Interactive setup** (full control over prompts):

```bash
curl -fsSL https://raw.githubusercontent.com/elohmeier/dotfiles/main/scripts/macos-fresh-setup.sh -o setup.sh
chmod +x setup.sh
./setup.sh
```

This will:

- Verify your current user has admin privileges
- Create a standard (non-admin) user account for daily use
- Install Xcode Command Line Tools
- Install Homebrew

After setup, log in as the standard user and manually install what you need:

```bash
brew install fish chezmoi
chezmoi init --apply https://github.com/elohmeier/dotfiles.git
```

## Quick Start (Existing User)

For existing macOS installations:

```bash
chezmoi init --apply https://github.com/elohmeier/dotfiles.git
```

## Manual Setup

```bash
# Initialize chezmoi with this repo
chezmoi init https://github.com/elohmeier/dotfiles.git

# Preview changes
chezmoi diff

# Apply dotfiles
chezmoi apply
```

## Scripts

Run packaged scripts directly with uv:

```bash
uvx --from git+https://github.com/elohmeier/dotfiles httpserve
pipx run --spec git+https://github.com/elohmeier/dotfiles httpserve
```

On Linux, `mount-media` and `umount-media` manage SD cards, USB drives, and
optical discs through UDisks, with authorization in the terminal:

```bash
mount-media                      # select the only removable filesystem
mount-media --device /dev/sr0     # mount an optical disc
umount-media --device /dev/sr0
```

When polkit would require a password (for example over SSH) and the rootful
Docker daemon is reachable, the commands mount as root through a privileged
container instead of prompting.

Fish completes options and available media devices. These commands are installed
by `home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl`.

## Agent Skills

Install or update the skills from [elohmeier/skills](https://github.com/elohmeier/skills) for Claude Code and Codex:

```bash
djust install-skills
```
