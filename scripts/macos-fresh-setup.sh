#!/usr/bin/env bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ADMIN_USER="$(whoami)" # Use current user as admin
STANDARD_USER="${STANDARD_USER:-}"
STANDARD_FULLNAME="${STANDARD_FULLNAME:-}"
HOMEBREW_PREFIX="/opt/homebrew"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if running as regular user (not root)
check_not_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "This script should NOT be run as root. Run as your admin user account."
    fi
}

# Check if user exists
user_exists() {
    local username=$1
    dscl . -list /Users | grep -q "^${username}$"
}

# Verify current user is admin
verify_admin_user() {
    log_info "Verifying current user '$ADMIN_USER' has admin privileges..."

    if ! dseditgroup -o checkmember -m "$ADMIN_USER" admin &>/dev/null; then
        log_error "Current user '$ADMIN_USER' is not an admin. Please run this script from an admin account."
    fi

    log_success "Current user '$ADMIN_USER' has admin privileges"
}

# Get list of standard (non-admin) users
get_standard_users() {
    local all_users admin_users standard_users

    # Get all regular users (UID >= 500)
    all_users=$(dscl . -list /Users UniqueID | awk '$2 >= 500 && $2 < 1000 {print $1}')

    # Get admin users
    admin_users=$(dscl . -read /Groups/admin GroupMembership 2>/dev/null | sed 's/GroupMembership: //')

    # Find non-admin users
    standard_users=""
    for user in $all_users; do
        if ! echo "$admin_users" | grep -qw "$user"; then
            standard_users="$standard_users $user"
        fi
    done

    echo "$standard_users" | xargs # trim whitespace
}

# Create standard user
create_standard_user() {
    # Auto-detect existing standard user if not specified
    if [[ -z "$STANDARD_USER" ]]; then
        local existing_standard_users
        existing_standard_users=$(get_standard_users)

        # Count the number of standard users
        local user_count
        user_count=$(echo "$existing_standard_users" | wc -w | xargs)

        if [[ "$user_count" -eq 1 ]]; then
            STANDARD_USER="$existing_standard_users"
            log_info "Auto-detected existing standard user: '$STANDARD_USER'"
            log_info "Standard user '$STANDARD_USER' already exists"
            return 0
        elif [[ "$user_count" -gt 1 ]]; then
            log_info "Multiple standard users found: $existing_standard_users"
            read -rp "Enter username for standard user to use: " STANDARD_USER
        else
            read -rp "Enter username for new standard user: " STANDARD_USER
        fi
    fi

    if [[ -z "$STANDARD_FULLNAME" ]]; then
        read -rp "Enter full name for standard user (default: $STANDARD_USER): " STANDARD_FULLNAME
        STANDARD_FULLNAME="${STANDARD_FULLNAME:-$STANDARD_USER}"
    fi

    if user_exists "$STANDARD_USER"; then
        log_info "Standard user '$STANDARD_USER' already exists"
        return 0
    fi

    log_info "Creating standard user '$STANDARD_USER'..."

    # Create standard user (non-admin) - requires admin authentication
    log_info "Setting up password for new user '$STANDARD_USER'"
    read -rsp "Enter password for new user '$STANDARD_USER': " user_password
    echo
    read -rsp "Confirm password for new user '$STANDARD_USER': " user_password_confirm
    echo

    if [[ "$user_password" != "$user_password_confirm" ]]; then
        log_error "Passwords do not match. Please try again."
    fi

    log_info "Creating user account. You will be prompted for your admin password..."
    if ! sudo sysadminctl -addUser "$STANDARD_USER" \
        -fullName "$STANDARD_FULLNAME" \
        -shell /bin/zsh \
        -password "$user_password"; then
        log_error "Failed to create user '$STANDARD_USER'. Please check the error message above."
    fi

    # Verify user was actually created
    if ! user_exists "$STANDARD_USER"; then
        log_error "User '$STANDARD_USER' was not created successfully."
    fi

    log_success "Standard user '$STANDARD_USER' created"
}

# Install Xcode Command Line Tools
install_xcode_tools() {
    if xcode-select -p &>/dev/null; then
        log_info "Xcode Command Line Tools already installed"
        return 0
    fi

    log_info "Installing Xcode Command Line Tools..."

    # Trigger the installation
    touch /tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress

    # Find the Command Line Tools package
    PROD=$(softwareupdate -l | grep "\*.*Command Line" | tail -n 1 | sed 's/^[^:]*: //')

    if [[ -n "$PROD" ]]; then
        softwareupdate -i "$PROD" --verbose
        rm /tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress
        log_success "Xcode Command Line Tools installed"
    else
        log_warning "Could not find Command Line Tools package. Please install manually."
    fi
}

# Install Homebrew
install_homebrew() {
    if [[ -x "$HOMEBREW_PREFIX/bin/brew" ]]; then
        log_info "Homebrew already installed"
        return 0
    fi

    log_info "Installing Homebrew..."

    # Download and run Homebrew installer
    if ! /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; then
        log_error "Failed to install Homebrew. Please check the error message above."
    fi

    # Verify Homebrew was installed
    if [[ ! -x "$HOMEBREW_PREFIX/bin/brew" ]]; then
        log_error "Homebrew installation failed - brew binary not found at $HOMEBREW_PREFIX/bin/brew"
    fi

    # Add Homebrew to standard user's PATH
    sudo -u "$STANDARD_USER" bash -c "echo 'eval \"\$($HOMEBREW_PREFIX/bin/brew shellenv)\"' >> /Users/$STANDARD_USER/.bash_profile"
    sudo -u "$STANDARD_USER" bash -c "echo 'eval \"\$($HOMEBREW_PREFIX/bin/brew shellenv)\"' >> /Users/$STANDARD_USER/.zprofile"

    log_success "Homebrew installed"
}

# Main execution flow
main() {
    cat <<EOF
╔════════════════════════════════════════╗
║     macOS Fresh Setup Script           ║
║     Privilege Separation Edition       ║
╚════════════════════════════════════════╝

This script will:
1. Verify current user has admin privileges
2. Create a standard (non-admin) user account
3. Install Xcode Command Line Tools
4. Install Homebrew

EOF

    check_not_root

    # Check current admin user
    log_info "Current admin user: '$ADMIN_USER'"

    # Auto-detect standard user before asking for confirmation
    if [[ -z "$STANDARD_USER" ]]; then
        local existing_standard_users
        existing_standard_users=$(get_standard_users)

        # Count the number of standard users
        local user_count
        user_count=$(echo "$existing_standard_users" | wc -w | xargs)

        if [[ "$user_count" -eq 1 ]]; then
            STANDARD_USER="$existing_standard_users"
            log_info "Auto-detected standard user: '$STANDARD_USER'"
        elif [[ "$user_count" -gt 1 ]]; then
            log_info "Multiple standard users found: $existing_standard_users"
        else
            log_info "No standard users found - will create one"
        fi
    fi

    echo # blank line for readability

    # Check if auto-confirm is set or if we can read from terminal
    if [[ "${AUTO_CONFIRM:-}" == "yes" ]]; then
        log_info "Auto-confirm enabled. Continuing..."
        confirm="y"
    elif [ -t 0 ]; then
        # Interactive mode - stdin is a terminal
        read -rp "Continue with setup? (y/N): " confirm
    else
        # Piped mode - auto-confirm since we can't interact
        log_info "Running via curl pipe. Auto-continuing..."
        log_info "To run interactively, download and run the script directly."
        confirm="y"
    fi

    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_info "Setup cancelled"
        exit 0
    fi

    # Phase 1: System Setup (as admin user)
    log_info "Phase 1: System Setup"
    verify_admin_user
    create_standard_user
    install_xcode_tools

    # Phase 2: User Environment Setup
    log_info "Phase 2: User Environment Setup"
    install_homebrew

    cat <<EOF

╔════════════════════════════════════════╗
║         Setup Complete!                ║
╚════════════════════════════════════════╝

Admin user: $ADMIN_USER
Standard user: $STANDARD_USER

Next steps:
1. Log out and log in as '$STANDARD_USER'
2. Open Terminal
3. Run: brew install fish chezmoi
4. Configure your shell and dotfiles as needed

EOF
}

# Run main function
main "$@"
