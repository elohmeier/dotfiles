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
chezmoi init https://github.com/elohmeier/dotfiles.git
sh "$(chezmoi source-path)/../scripts/bootstrap.sh"
```

## Quick Start (Existing User)

For existing macOS installations:

```bash
chezmoi init https://github.com/elohmeier/dotfiles.git
sh "$(chezmoi source-path)/../scripts/bootstrap.sh"
```

Bootstrap installs the base Homebrew/APK packages first, then starts a fresh
`chezmoi apply` so templates detect the newly installed tools. On other systems,
install the tools you need before applying the configuration.

On Workbrew-managed Macs, the package hooks use `/opt/workbrew/bin/brew`.
Keep that wrapper ahead of `/opt/homebrew/bin` on `PATH`.
The font hook uses cask metadata to install fonts in `~/Library/Fonts` as the
login user, so they do not appear as installed casks.

## Manual Setup

```bash
# Initialize chezmoi with this repo
chezmoi init https://github.com/elohmeier/dotfiles.git

# Preview changes
chezmoi --skip-secrets diff

# Install base packages, then apply dotfiles
sh "$(chezmoi source-path)/../scripts/bootstrap.sh"
```

Subsequent updates use `chezmoi update` or `chezmoi apply` as usual.

## Configuration

Fish activates mise once and skips rbenv's startup rehash. Run `rbenv rehash`
after installing Ruby executables when the installer has not already done so.
Fish universal defaults and Ghostty terminfo are updated only when their inputs
change.

Neovim uses Ruff for Python linting and ty for type checking. To use basedpyright
in a project, set `NVIM_PYTHON_LSP = "basedpyright"` in its mise `[env]` table
before starting Neovim.

macOS application config links under `~/Library` are managed directly by chezmoi.
Move any existing directories at those link paths aside before the first apply.

Run the dotfiles checks with chezmoi, Fish, Bash, Zsh, and jq installed:

```sh
uv run --locked pytest -q tests/test_chezmoi.py
```

The checks render macOS, Linux, and WSL configurations across all four themes in
an isolated home, check shell syntax, and parse JSON, TOML, and YAML. Installation
hooks are rendered without executing them. Pre-commit and CI use Ruff from
`uv.lock`.

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

`agent-session` searches Claude Code, Pi and Codex sessions across host and sandbox
stores. Run it without arguments for the fzf picker, with a transcript preview,
first prompt, latest reply and matching message. Enter opens the resume, preview,
fork and copy actions. In the picker, Ctrl-D selects the current directory,
Ctrl-G the repository (including worktrees), Ctrl-B the recorded branch and
Ctrl-A all sessions. Queries support `agent:pi`, `store:codex:sandbox`,
`b:feature` and `m:opus` filters, words and quoted phrases; the final unquoted
word also matches prefixes.

```sh
agent-session
agent-session --scope repo --query 'migration agent:pi'
agent-session list --all
agent-session search 'flaky test' --scope repo --json
agent-session show claude:host:<id-prefix>
agent-session show pi:<id-prefix> --start -10 --tools --json
agent-session fork pi:<id-prefix> --resume
agent-session copy claude:host:<id-prefix> --to pi
agent-session copy pi:<id-prefix> --to codex:sandbox --resume
agent-session copy claude:host:<id-prefix> --to codex --resume -- --yolo
agent-session resume codex:host:<id-prefix> -- --yolo
agent-session resume pi:<id-prefix> --print
```

`show` reads full history, including messages before compaction and abandoned
branches. `--context` selects only the active context that a cross-agent copy
would transfer. Tool inputs and outputs are folded unless `--tools` is given.
Pages default to 20 messages and 16,000 text characters; `--start`, `--limit`,
`--offset` and `--chars` control paging. JSON includes a `next` cursor with
`start` and `offset`, plus block types, tool IDs and error status. Images are
represented by metadata rather than base64 data. Search JSON includes
`match_line`, which `show --match-line` opens in context. Search covers titles,
conversation text, tool inputs and recorded metadata, excluding tool outputs
and image data.

`copy --resume` imports the session and immediately launches the destination
agent in its recorded working directory. Arguments after `--` are forwarded to
the agent unchanged, for example Codex's `--yolo` or `--model` options. This also
works with `resume` for sessions that have already been copied.

Cross-agent copies create a new session with the active conversation context, existing
compaction summaries and historical tool calls/results rendered as text. The
source session stays unchanged. Claude and Pi retain inline images; Codex's
native importer replaces images with omission notices. Copies report message
count, approximate text tokens, flattened tools and omitted images before
writing; `--dry-run` reports without creating a session. Copies keep all available
context by default. `--max-tokens N` sets an optional text budget (UTF-8 bytes
divided by four, excluding images). Opaque compactions and contexts exceeding an
explicit budget fail unless `--allow-partial` is given; partial copies mark unavailable context
and omit older turns when needed. `--tool-output-limit N` clips each tool result
to N characters plus an omission notice, keeping both ends. Repeatable
`--redact REGEX` replaces matches in transferred text. Models, permissions, instructions, running tools and
file checkpoints belong to the destination agent.

`fork`, and `copy` to the same agent, preserve native records, tool calls,
images and compactions under a new session ID. Codex forks use its app-server
fork API; Claude and Pi retain their native parent references. Forks and
cross-agent continuations record their source store/session and are grouped
under their parent in listings and the picker.

Host stores honor `CLAUDE_CONFIG_DIR`, `PI_CODING_AGENT_DIR`,
`PI_CODING_AGENT_SESSION_DIR` and `CODEX_HOME`. Claude/Codex sandbox stores live
under `${XDG_DATA_HOME:-~/.local/share}/agent-sandbox`; Pi shares its host store.
Use `claude:sandbox` or `codex:sandbox` as a destination to resume through
`mise run agent:<agent>`. Plain `claude` and `codex` destinations select the host.
Codex copies require the Codex CLI and use its native session importer; sandbox
copies also require the shared agent container.

The disposable SQLite/FTS5 index lives under
`${XDG_CACHE_HOME:-~/.cache}/agent-session/`. Commands refresh changed transcripts
from their last complete-line checkpoint and detect replaced/rewritten files.
`agent-session reindex` rebuilds it from the native transcripts; no daemon or
sync service is required. Branch filters use recorded metadata rather than
assuming a session ran on the checkout's current branch. Outside a repository,
repository/branch scope falls back to all sessions; a detached HEAD falls back
to repository scope.

`resume --print` includes the working directory, store environment and quoted
agent arguments without launching the agent. `agent-session --print` combines
this with the picker. Fish binds Ctrl-] to insert the selected resume command
for review, and completes subcommands, options, destinations and current-directory
session references. The CLI is installed by
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

Skills live in [skills/](skills/README.md). Install or update them for Claude Code and Codex from this checkout:

```bash
djust install-skills
```

Run this again after editing skills or pulling updates; installed skills are copies.

The Python Grafana utilities are installed by chezmoi; build the Go/Node ones with `djust install-grafana-tools`. See [Grafana tools](docs/grafana-tools.md) for commands, validation, and stable-release updates.

Renovate updates Python, npm, Go, Docker images, pre-commit hooks, dprint plugins,
the container's agent CLIs, mise, uv, Python standalone builds, and tunneldigger's
pinned upstream commit. Updates,
including major versions and weekly lockfile maintenance, automatically
squash-merge after the required `CI` check passes. CI tests Python on Linux and
macOS, renders the dotfiles for all supported platforms and themes, validates
Grafana pins and tools, and builds and tests the agent/proxy
images. Python CLI installation in
`home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl` uses constraints
exported from `uv.lock`.

Grafana and its React peers remain on the coordinated `tools/update-grafana.mjs`
updater. Renovate leaves the project's supported Python floor unchanged.
Floating Homebrew/APK packages and global tools installed with `@latest` are
updated by their existing installation commands. Apply merged dotfiles with
`chezmoi update`; rebuild the agent images with `mise run agent:build`.
