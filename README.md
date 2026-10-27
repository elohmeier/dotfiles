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

On Workbrew-managed Macs, the package hooks use `/opt/workbrew/bin/brew`.
Keep that wrapper ahead of `/opt/homebrew/bin` on `PATH`.
The font hook uses cask metadata to install fonts in `~/Library/Fonts` as the
login user, so they do not appear as installed casks.

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

### Agent sessions

`agent-session` lists Claude Code, Pi and Codex sessions for the current directory.
Run it without arguments to select a session and preview, resume or copy it:

```sh
agent-session
agent-session list --all
agent-session show claude:host:<id-prefix>
agent-session copy claude:host:<id-prefix> --to pi
agent-session copy pi:<id-prefix> --to codex:sandbox --resume
```

Copies create a new session with the active conversation context, existing
compaction summaries and historical tool calls/results rendered as text. The
source session stays unchanged. Claude and Pi retain inline images; Codex's
native importer replaces images with omission notices. Opaque Codex compactions
cannot be transferred. Models, permissions, instructions, running tools and
file checkpoints belong to the destination agent.

Host stores honor `CLAUDE_CONFIG_DIR`, `PI_CODING_AGENT_DIR`,
`PI_CODING_AGENT_SESSION_DIR` and `CODEX_HOME`. Claude/Codex sandbox stores live
under `${XDG_DATA_HOME:-~/.local/share}/agent-sandbox`; Pi shares its host store.
Use `claude:sandbox` or `codex:sandbox` as a destination to resume through
`mise run agent:<agent>`. Plain `claude` and `codex` destinations select the host.
Codex copies require the Codex CLI and use its native session importer; sandbox
copies also require the shared agent container.

Fish completes subcommands, options, destinations and current-directory session
references. The CLI is installed by
`home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl`.

### Btrfs home snapshots (Fedora Atomic / Bluefin)

Enable 30 daily read-only snapshots of the `/home` subvolume:

```bash
./scripts/setup-btrfs-home-snapshots.sh
```

Set `SNAPSHOT_CALENDAR` and `SNAPSHOT_KEEP` to change the schedule and retention.
Snapshots live in the root-only `/home/.snapshots` subvolume and do not replace
an off-device backup.

### OOM protection for remote access (Linux)

Keep tailscaled and sshd responsive under memory pressure (MGLRU thrash
protection, memory.min reservations, user session caps, systemd-oomd swap kill):

```bash
./scripts/setup-oom-protection.sh
```

Large models run via the optional `systemctl --user start llama-server` unit,
which caps memory and is the preferred OOM victim. Override its arguments with
`LLAMA_ARGS=...` in `~/.config/llama-server.env`.

## Agent Skills

Install or update the skills from [elohmeier/skills](https://github.com/elohmeier/skills) for Claude Code and Codex:

```bash
djust install-skills
```

The Python Grafana utilities are installed by chezmoi; build the Go/Node ones with `djust install-grafana-tools`. See [Grafana tools](docs/grafana-tools.md) for commands, validation, and stable-release updates.

Renovate updates Python, npm, Go, Docker images, pre-commit hooks, dprint plugins,
the container's agent CLIs, mise, uv, Python standalone builds, and tunneldigger's
pinned upstream commit. Updates,
including major versions and weekly lockfile maintenance, automatically
squash-merge after the required `CI` check passes. CI tests Python on Linux and
macOS, validates Grafana pins and tools, and builds and tests the agent/proxy
images. Python CLI installation in
`home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl` uses constraints
exported from `uv.lock`.

Grafana and its React peers remain on the coordinated `tools/update-grafana.mjs`
updater. Renovate leaves the project's supported Python floor unchanged.
Floating Homebrew/APK packages and global tools installed with `@latest` are
updated by their existing installation commands. Apply merged dotfiles with
`chezmoi update`; rebuild the agent images with `mise run agent:build`.
