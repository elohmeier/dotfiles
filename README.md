# Dotfiles

Personal dotfiles for macOS setup and configuration.

## Fresh macOS Installation Guide

This guide will help you set up a new Mac with these dotfiles.

### Initial Setup

1. **Create Admin Account**
   - During the initial macOS setup, create an administrator account
   - This account will be used for system-level changes only

2. **Run Initial Setup Script as Admin**
   - While logged in as the admin user, run:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/elohmeier/dotfiles/main/initial-setup.sh | bash
   ```
   - This will install Homebrew and other system dependencies
   - Restart your computer after the script completes

3. **Create Standard User Account**
   - Go to System Settings → Users & Groups
   - Click "Add User" (you'll need to authenticate)
   - Create a standard (non-admin) account for daily use
   - Log out of the admin account and log in to your new standard user account

4. **Clone Dotfiles Repository as Standard User**
   ```bash
   mkdir -p ~/Dotfiles
   git clone https://github.com/elohmeier/dotfiles.git ~/Dotfiles
   cd ~/Dotfiles
   ```

5. **Set Up User Configuration**
   ```bash
   ./user-setup.sh
   ```

6. **Change Default Shell to Fish**
   ```bash
   chsh -s $(which fish)
   ```
   - You'll need to enter your password
   - Log out and log back in for the change to take effect

## Managing Dotfiles

This repository uses the [dotfiles](https://github.com/jbernard/dotfiles) tool to manage symlinks between the repository and your home directory.

- To add a new dotfile: `dotfiles --add ~/.filename`
- To sync all dotfiles: `dotfiles --sync`
- To list managed dotfiles: `dotfiles --list`
- To check for unsynced dotfiles: `dotfiles --check`

Configuration is stored in `.dotfilesrc` at the root of the repository.

## What's Included

- Fish shell configuration
- Neovim setup with LazyVim
- Git configuration
- Homebrew packages and applications
- macOS system preferences

## Maintenance

- Backup Homebrew packages: `./backup-brew.sh`
- Backup Cargo packages: `./backup-cargo.sh`
- Backup UV tools: `./backup-uv-tools.sh`
