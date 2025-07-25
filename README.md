# Dotfiles

Personal dotfiles managed with [chezmoi](https://www.chezmoi.io/).

## Quick Start

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
