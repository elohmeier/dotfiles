# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a personal dotfiles repository managed by **chezmoi**, a cross-machine dotfile manager. The repository contains configuration files for various development tools and applications, with proper secret management using SOPS and age encryption.

## Common Commands

### Chezmoi Operations

```bash
# Apply all dotfiles to home directory
chezmoi apply

# Preview changes before applying
chezmoi diff

# Add a new file to manage
chezmoi add ~/.config/someapp/config

# Edit a managed file (automatically re-encrypts if needed)
chezmoi edit ~/.config/someapp/config

# Open shell in source directory
chezmoi cd

# Update chezmoi data (re-runs template processing)
chezmoi init --apply
```

### Secret Management

```bash
# Decrypt and view all secrets
./scripts/chesops.sh

# Get specific secret value using yq path
./scripts/chesops.sh ".anthropic.api_key"

# Edit secrets file (will re-encrypt on save)
sops secrets.yaml
```

### Code Formatting

```bash
# Format all supported files (JSON, Markdown, TOML, YAML)
dprint fmt

# Check formatting without changing files
dprint check

# Format Lua files in nvim config
stylua home/dot_config/nvim/
```

## Architecture & Structure

### Directory Layout

- **`home/`** - Root directory for all managed dotfiles (set by `.chezmoiroot`)
  - **`dot_config/`** - XDG config directory (`~/.config/`)
  - **`dot_ssh/`** - SSH configuration
  - Template files use `.tmpl` extension and Go template syntax
  - Encrypted files have `.age` extension

### Chezmoi Naming Conventions

Chezmoi uses special prefixes in the source repository to handle dotfiles and directories:

- **`dot_`** prefix becomes `.` when applied (e.g., `dot_config` → `.config`)
- **`private_`** prefix sets 0600 permissions (user read/write only)
- **`readonly_`** prefix sets 0400 permissions (user read only)
- **`executable_`** prefix makes files executable
- **`.tmpl`** suffix indicates a template file processed with Go templates

Examples:

- `home/dot_config/git/config` → `~/.config/git/config`
- `home/dot_gitignore` → `~/.gitignore`
- `home/private_dot_ssh/` → `~/.ssh/` (with restricted permissions)

### Key Components

1. **Secret Management**
   - Secrets stored in `secrets.yaml` (SOPS-encrypted)
   - Age encryption keys at `~/Library/Application Support/sops/age/keys.txt`
   - `chesops.sh` script provides convenient secret access

2. **Templating System**
   - Chezmoi uses Go templates for dynamic configuration
   - Template data available:
     - `{{ .email }}` - User email
     - `{{ .displayConfig }}` - Current display setup (internal/external)
     - `{{ secret "path.to.secret" }}` - Access encrypted secrets

3. **Display Detection**
   - `get-display-config.sh` detects macOS display configuration
   - Used in templates to adjust configurations based on display setup

### Important Files

- **`.chezmoi.toml.tmpl`** - Main chezmoi configuration
- **`secrets.yaml`** - Encrypted secrets (API keys, tokens)
- **`dprint.json`** - Multi-language formatter configuration
- **`home/dot_config/git/config.tmpl`** - Git configuration with delta integration
- **`home/dot_config/nvim/`** - LazyVim-based Neovim configuration

### Neovim Plugin Management

This configuration uses **Lazy.nvim** (not LazyVim distro) for plugin management. Important guidelines:

1. **One Plugin Per File Rule**
   - Each plugin should have its own file in `home/dot_config/nvim/lua/plugins/`
   - Never declare the same plugin in multiple files - Lazy.nvim merges specs which can cause conflicts
   - Example: Don't create `templates.lua` with `telescope.nvim` if `telescope.lua` already exists

2. **Plugin Specification Patterns**
   ```lua
   return {
     "author/plugin-name",
     dependencies = { ... },     -- Other plugins this depends on
     lazy = false,              -- Set to false for immediate loading (e.g., colorschemes)
     event = "VeryLazy",        -- Or specific events like "BufReadPre"
     config = function() ... end, -- Configuration function
     opts = { ... },            -- Or configuration table
     keys = { ... },            -- Lazy-load on specific keybinds
   }
   ```

3. **Adding Functionality to Existing Plugins**
   - If extending an existing plugin (e.g., adding telescope pickers), modify the existing file
   - Don't create a new file that returns the same plugin
   - Use the plugin's `config` function to add keymaps and functionality

4. **Keybinding Best Practices**
   - Define keybindings in the plugin's `config` function using `vim.keymap.set()`
   - Or use the `keys` table for lazy-loaded keybindings
   - Check existing keybindings with `:Telescope keymaps` to avoid conflicts

5. **Debugging Plugin Issues**
   - Use `:Lazy` to see loaded plugins and their source files
   - Check for duplicate plugin specifications if keybindings stop working
   - Look for multiple files returning the same plugin name

### Working with Encrypted Files

Files with `.age` extension are encrypted. To work with them:

1. Chezmoi automatically decrypts when applying
2. Use `chezmoi edit` to modify (auto-encrypts on save)
3. Never commit decrypted versions

### Theme Consistency

TokyoNight theme is used across multiple tools:

- bat (syntax highlighting)
- delta (git diffs)
- k9s (Kubernetes UI)
- ghostty (terminal)
- Neovim

When adding new tool configurations, prefer TokyoNight variants for consistency.

## Package Management

This repository includes automated package installation via Homebrew. The script `home/.chezmoiscripts/run_onchange_before_install-packages.sh.tmpl` automatically installs required packages when the file changes.

### Core Packages (automatically installed)

**Development Tools:**

- `neovim`, `lazygit`, `gh` - Editor and Git tools
- `go`, `bun`, `pnpm`, `uv`, `rustup` - Language runtimes
- `bash-language-server`, `lua-language-server`, `jsonnet-language-server` - LSP servers
- `shellcheck`, `shfmt`, `stylua`, `dprint` - Linters and formatters

**CLI Utilities:**

- `bat`, `eza`, `fd`, `ripgrep`, `fzf` - Modern Unix tool replacements
- `btop`, `ncdu` - System monitoring
- `yazi` - Terminal file manager
- `atuin` - Shell history sync
- `zoxide` - Smart directory navigation

**Infrastructure Tools:**

- `k9s`, `helm` - Kubernetes management
- `opentofu` - Infrastructure as code
- `sops` - Secret management
- `orbstack` - Container runtime (macOS)

**Fonts:**

- `font-ibm-plex-mono`, `font-ibm-plex-sans`, `font-spleen`

### Adding New Packages

To add new packages, edit the brew lists in `home/.chezmoiscripts/run_onchange_before_install-packages.sh.tmpl`:

- Add to `$brews` list for formulae
- Add to `$casks` list for GUI applications
- The script uses `brew bundle` and will run automatically when chezmoi detects changes

## Scripts

### Utility Scripts (`scripts/`)

- **`chesops.sh`** - SOPS wrapper for decrypting secrets from `secrets.yaml`
  ```bash
  ./scripts/chesops.sh                    # View all secrets
  ./scripts/chesops.sh ".path.to.secret"  # Get specific secret
  ```

- **`get-display-config.sh`** - Detects display configuration on macOS
  - Returns "internal" or "external" based on connected displays
  - Used in templates for conditional configuration

### Chezmoi Scripts (`home/.chezmoiscripts/`)

These scripts run automatically during `chezmoi apply`:

- **`run_onchange_before_install-packages.sh.tmpl`** - Package installation
  - Runs before applying dotfiles when the script changes
  - Installs Homebrew formulae and casks
  - Manages development tools, CLI utilities, and applications

- **`run_onchange_after_configure-defaults.sh`** - macOS system preferences
  - Runs after applying dotfiles when the script changes
  - Configures keyboard repeat rates, Finder preferences, Dock settings
  - Sets application-specific defaults (e.g., VS Code key repeat)

- **`run_onchange_after_link-macos-library.sh`** - Application support symlinks
  - Runs after applying dotfiles when the script changes
  - Creates symlinks from `~/Library/Application Support/` to `~/.config/`
  - Handles applications that expect macOS-style paths (lazygit, k9s, process-compose)
  - Creates backups before replacing existing directories

- **`run_onchange_after_bat-cache.sh.tmpl`** - Rebuild bat syntax highlighting cache
  - Runs after applying dotfiles when bat themes change
  - Automatically rebuilds bat cache when themes are added or modified
  - Uses template hash to detect changes in theme files
