#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting user configuration setup...${NC}"

# Check if running as root/sudo and exit if true
if sudo -v &> /dev/null; then
  echo -e "${RED}This script should be run by a standard user without sudo privileges.${NC}"
  echo -e "${RED}Please create and log in as a standard user account.${NC}"
  exit 1
fi

# Set up Fish shell paths
echo -e "${BLUE}Setting up Fish shell paths...${NC}"
# Get the user's home directory
HOME_DIR="$HOME"
DOTFILES_DIR="$HOME_DIR/Dotfiles"

# Check if Fish is installed
if ! command -v fish &> /dev/null; then
  echo -e "${RED}Fish shell is not installed. Please run the initial-setup.sh script first.${NC}"
  exit 1
fi

# Set Fish user paths
fish -c "
  # Clear existing paths to avoid duplicates
  set -U fish_user_paths

  # Add paths using fish_add_path (in reverse order to get the right precedence)
  fish_add_path -U /opt/homebrew/bin
  fish_add_path -U $HOME_DIR/.local/bin
  fish_add_path -U $DOTFILES_DIR/bin
  fish_add_path -U $HOME_DIR/.cargo/bin
"

echo -e "${GREEN}Fish shell paths configured.${NC}"

echo -e "${GREEN}User configuration setup complete!${NC}"
echo -e "${GREEN}Please restart your terminal to ensure all changes take effect.${NC}"
