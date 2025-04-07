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


echo -e "${GREEN}User configuration setup complete!${NC}"
echo -e "${GREEN}Please restart your terminal to ensure all changes take effect.${NC}"
