#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting initial system setup...${NC}"

# Check if running as non-admin user
if ! sudo -v &> /dev/null; then
  echo -e "${RED}This script must be run by an admin user with sudo privileges.${NC}"
  exit 1
fi

# Check if running as root and exit if true
if [ "$EUID" -eq 0 ]; then
  echo -e "${RED}Please do not run this script as root. Run as admin user instead.${NC}"
  exit 1
fi

# Install Command Line Tools if not installed
if ! xcode-select -p &> /dev/null; then
  echo -e "${BLUE}Installing Command Line Tools...${NC}"
  xcode-select --install
  echo -e "${GREEN}Please wait for Command Line Tools installation to complete, then press Enter to continue...${NC}"
  read -r
fi

# Install Homebrew if not installed
if ! command -v brew &> /dev/null; then
  echo -e "${BLUE}Installing Homebrew...${NC}"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Add Homebrew to PATH for the current session
  if [[ $(uname -m) == "arm64" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  else
    eval "$(/usr/local/bin/brew shellenv)"
  fi
else
  echo -e "${GREEN}Homebrew already installed.${NC}"
fi

# Install Fish shell
echo -e "${BLUE}Installing Fish shell...${NC}"
brew install fish

# Add Fish to /etc/shells if not already there
if ! grep -q "$(which fish)" /etc/shells; then
  echo -e "${BLUE}Adding Fish to /etc/shells...${NC}"
  which fish | sudo tee -a /etc/shells
fi

# Configure Homebrew environment
echo -e "${BLUE}Configuring Homebrew environment...${NC}"
# Ask for the username since we need the actual user who will use the system
read -pr "Please enter the username for Homebrew configuration: " USERNAME

# Create Homebrew environment file
BREW_ENV_DIR="$(brew --prefix)/etc/homebrew"
BREW_ENV_FILE="${BREW_ENV_DIR}/brew.env"

# Create directory if it doesn't exist
sudo mkdir -p "$BREW_ENV_DIR"

# Write environment variables to file
cat > /tmp/brew.env << EOF
HOMEBREW_NO_INSECURE_REDIRECT=1
HOMEBREW_CASK_OPTS=--appdir=/Users/${USERNAME}/Applications
HOMEBREW_NO_ENV_HINTS=1
EOF

# Move the file to the correct location with proper permissions
sudo mv /tmp/brew.env "$BREW_ENV_FILE"
sudo chown root:admin "$BREW_ENV_FILE"
sudo chmod 644 "$BREW_ENV_FILE"

echo -e "${GREEN}Homebrew environment configured.${NC}"

# Change ownership of Homebrew prefix to the user
echo -e "${BLUE}Setting ownership of Homebrew prefix to ${USERNAME}:staff...${NC}"
BREW_PREFIX=$(brew --prefix)
sudo chown -R "${USERNAME}:staff" "$BREW_PREFIX"
echo -e "${GREEN}Homebrew ownership updated.${NC}"
