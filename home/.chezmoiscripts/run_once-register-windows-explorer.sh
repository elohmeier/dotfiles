#!/bin/sh

set -e

if [ ! -x /mnt/c/Windows/explorer.exe ]; then
  exit 0
fi

xdg-mime default windows-explorer-wsl.desktop inode/directory

if command -v update-desktop-database >/dev/null 2>&1; then
  applications_dir="${HOME}/.local/share/applications"
  mkdir -p "${applications_dir}"
  update-desktop-database "${applications_dir}"
fi
