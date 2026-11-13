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
brew install fish chezmoi just
chezmoi init https://github.com/elohmeier/dotfiles.git
sh "$(chezmoi source-path)/../scripts/bootstrap.sh"
```

## Quick Start (Existing User)

For existing macOS installations:

```bash
chezmoi init https://github.com/elohmeier/dotfiles.git
sh "$(chezmoi source-path)/../scripts/bootstrap.sh"
```

Chezmoi does not install Homebrew packages or fonts automatically. Use
`djust install-packages` for base packages and `djust install-fonts` for fonts.
Base package installation skips commands already in `PATH`, including `python3`
on Alpine. It includes ripgrep (`rg`) and excludes Node.js/npm.
Run `chezmoi apply` afterwards so templates detect the newly installed tools.
Install Fish and just before using `djust` in Fish.

Bootstrap installs base APK packages on Alpine before applying the dotfiles.
On other systems, install the tools you need before applying the configuration.

On Workbrew-managed Macs, `djust install-packages` uses `/opt/workbrew/bin/brew`.
Keep that wrapper ahead of `/opt/homebrew/bin` on `PATH`.
`djust install-fonts` uses cask metadata to install fonts in `~/Library/Fonts` as the
login user, so they do not appear as installed casks.

On Linux, `djust install-fonts` downloads IBM Plex Mono, IBM Plex Sans, and Spleen
using Homebrew's public cask metadata and verifies their SHA-256 checksums. It
installs the OTF files in `${XDG_DATA_HOME:-$HOME/.local/share}/fonts`, restores
SELinux labels when `restorecon` is available, and refreshes the font cache.
Requires `curl`, `jq`, `unzip`, GNU `tar`, and `fc-cache`; Homebrew is not required.
No root access, package layering, or reboot is needed on Fedora Atomic/secureblue.

## Manual Setup

```bash
# Initialize chezmoi with this repo
chezmoi init https://github.com/elohmeier/dotfiles.git

# Preview changes
chezmoi --skip-secrets diff

# Apply dotfiles (also installs base APK packages on Alpine)
sh "$(chezmoi source-path)/../scripts/bootstrap.sh"
```

Subsequent updates use `chezmoi update` or `chezmoi apply` as usual.

### TPM-backed SSH on Linux

On a Linux machine with TPM 2.0 and a systemd user session:

```sh
brew install elohmeier/tap/ssh-tpm-agent
chezmoi apply
djust setup-tpm-udev
djust setup-tpm-ssh
```

`setup-tpm-udev` uses [run0](https://www.freedesktop.org/software/systemd/man/latest/run0.html)
(systemd 256+) and polkit for administrator authorization. Run it as your normal
user. It installs `/etc/udev/rules.d/99-tpm.rules`, granting that user's UID
read/write access to `/dev/tpmrm0` with mode `0600`, and applies the rule immediately.
No wheel membership or logout is needed; access also works over SSH. This is a
single-user rule: rerunning it for another user replaces the owner. Chezmoi hooks
do not change system TPM permissions.

`setup-tpm-ssh` checks prerequisites, creates `~/.ssh/id_ecdsa.tpm` and
`~/.ssh/id_ecdsa.pub`, starts the agent, and offers GitHub registration. It reuses
an existing TPM key and refuses to overwrite an existing software key. The TPM
private key is bound to this machine; copying the `.tpm` file to another machine
does not make it usable there.

For passphrase-protected keys, chezmoi sets `SSH_ASKPASS` in the agent service
using a standalone `ssh-askpass` or, when `pinentry-gnome3` is installed, the
managed `~/.local/bin/ssh-tpm-askpass` adapter. GCR's internal `gcr*-ssh-askpass`
programs require a private GCR socket and cannot be used directly.
The Linux hook reloads systemd and restarts a running TPM agent when the rendered
service configuration changes.

Open a new terminal after setup and run `ssh-add -l`. Fish selects the TPM agent
for local sessions and preserves forwarded agents over SSH. To check this
machine's TPM agent explicitly, including over SSH:

```sh
env SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-tpm-agent.sock" ssh-add -l
```

If setup fails:

- **Recipe missing:** run `chezmoi apply` to refresh `djust` recipes after updating
  this checkout or installing tools. Both TPM setup recipes are available on Linux.
- **No `/dev/tpmrm0`:** enable TPM/fTPM/PTT in firmware, or expose a TPM to the VM.
- **Permission denied:** run `djust setup-tpm-udev`, then retry `djust setup-tpm-ssh`.
- **run0 missing or authorization fails:** install systemd 256+ and polkit using
  your distribution's package manager. Retry from an interactive login session
  with an administrator available to approve the polkit prompt. Inspect
  `systemctl status polkit.service systemd-udevd.service`.
- **Agent failure:** inspect `journalctl --user -b -u ssh-tpm-agent.service`.
- **GitHub registration fails:** run `gh auth login -h github.com`, then retry, or
  paste `~/.ssh/id_ecdsa.pub` at <https://github.com/settings/ssh/new>.

## Configuration

Fish activates mise once and skips rbenv's startup rehash. Run `rbenv rehash`
after installing Ruby executables when the installer has not already done so.
Fish universal defaults and Ghostty terminfo are updated only when their inputs
change.

Chezmoi adds [GitHub's official SSH host keys](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)
to `~/.ssh/known_hosts`, preserving existing entries without adding duplicates.

The password store uses passage (age). Its recipients are listed in
`.age-recipients` in the password-store repository; the identity lives in
`~/.passage/identities` (Secure Enclave key on macOS, TPM key on Linux) and is
unlocked once per boot through the age-plugin-se / age-plugin-tpm agent.

`djust install-nvim` installs Neovim, Tree-sitter CLI, Git, and ripgrep for code
browsing, skipping commands already in `PATH`. Tree-sitter parser installation
also needs a C compiler, curl, and tar on the system.

`djust install-nvim-extras` adds language servers, formatters, notebook conversion,
and images. Neovim activates language servers, notebook conversion, and images
when their executables are available; format-on-save skips buffers without an
available formatter. Run `chezmoi apply` after installing extras to enable Git's
notebook diff settings, then restart Neovim. `djust install-extras` includes only
the basic Neovim setup; agent CLIs remain in `djust install-npm-tools`.

The Neovim extras use Ruff for Python linting and ty for type checking. To use
basedpyright in a project, install it separately with `brew install basedpyright`
and set `NVIM_PYTHON_LSP = "basedpyright"` in its mise `[env]` table before starting
Neovim.

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

### Shell helpers and URL inspection

```fish
mkcd 'new project'  # create missing parents and enter the directory
tempe              # start a Fish subshell in a new temporary directory
scratch            # open a temporary file using $EDITOR
cpwd               # copy the current directory using clip
url 'https://example.com/path?tag=one&tag=two&empty=#section'
ocr screenshot.png # macOS: extract image text using Apple Vision
getsubs 'https://www.youtube.com/watch?v=VIDEO_ID' > transcript.txt
getsubs --lang de 'https://www.youtube.com/watch?v=VIDEO_ID'
theme              # show the current theme
theme cyberdream   # switch themed dotfiles and refresh Fish/tmux
theme --dry-run tokyonight_day
timer 10m          # ring and notify after ten minutes
waitfor --notify 1234 # wait for a process, then notify
```

The Fish helpers are managed by chezmoi. In `tempe`, press Ctrl-D on an empty
command line or run `exit` to return to the original shell and directory.
Temporary files and directories remain available after use and follow the
system's temporary-file cleanup policy.
`url` prints URL components and decoded query parameters, preserving repeated
keys and empty values, without making a network request. It is installed through
the existing uv tools hook in `home/.chezmoiscripts/`.

`ocr` requires Swift and is installed only on macOS. `getsubs` requires `yt-dlp`,
prefers official subtitles, and falls back to automatic captions. It prints plain
text with timestamps, markup, and consecutive duplicate lines removed.

`theme` accepts `tokyonight_day`, `tokyonight_night`, `cyberdream_light`, or
`cyberdream`. It preserves other chezmoi settings and applies only managed
templates that reference themes, including their reload hooks. The Fish function
also refreshes the current shell's colors. Reload Ghostty's configuration and
restart existing editors to pick up the change there.

`timer` accepts seconds or a number followed by `s`, `m`, or `h`. Timers and
`waitfor --notify` use the existing Pushover helper when configured, otherwise
macOS notifications or `notify-send` when available, plus a terminal bell.
`waitfor` inhibits sleep using `caffeinate` on macOS or `systemd-inhibit` on Linux
when available. It detects completion but cannot recover another process's exit
status. Use Fish's `timer 10m &` to run a timer in the background.

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

`agent-session serve` opens a web explorer on `http://127.0.0.1:8065`. Pick up
shows the latest session of every workspace (repository, including worktrees,
or directory). Workspace and search views list sessions with forks under their
parent; a session shows its transcript with tool calls folded, opened at the
last exchange or at the search match, and its resume command. `/` focuses
search, `j`/`k` move through the list and `y` copies the command. The UI is a
SvelteKit/shadcn-svelte app in `tools/agent-session-ui`; the install script
builds it into `scripts/agent_session_ui/` before installing the CLI. For UI
work, run `agent-session serve` and `pnpm dev` in `tools/agent-session-ui`,
which proxies `/api` to it.

### Taskwarrior viewer

`taskwarrior-viewer` serves a read-only Svelte task browser at
`http://127.0.0.1:8066` (`--host` and `--port` override the bind address).
It uses the active Taskwarrior configuration, including `TASKRC` and `TASKDATA`.
Search titles, notes, source IDs and metadata; filter by status, source,
project or Logseq page; and select a task to inspect its annotations, source
links, dates, related tasks and original attributes. Filters and selected task
UUIDs are saved in the URL. `/` focuses search, `j`/`k` navigate tasks, and
Escape closes the details.

Project and Logseq-page pickers support text search. Active search/source/project/
page filters appear as removable chips in both tabs, with a shared clear action;
the search field also has a clear button. On desktop, drag or keyboard-resize the
divider between the task list and details; its width is remembered locally.
On mobile, filters open in a sheet with keyboard focus containment and restoration.

The default **Ready** view excludes future wait dates, future scheduled dates
and unresolved dependencies. **All open**, **Hidden until**, **Scheduled** and
**Blocked** views expose the other workflow states independently of the raw
exported status. Inbox review shows open Inbox actions with source page/list,
Logseq ancestor context, priority and age, initially sorted oldest first.

Sources include Apple Reminders, with original lists kept separate from curated
projects. Area filters and project filters include subprojects; disable
**Include subprojects** for an exact match. Tag filters and workflow shortcuts
cover `next`, `delegated`, `verify` and `steuer`. Follow-up sorting uses scheduled
or wait dates; details show `waitingfor`, source context, closure outcomes and
merge links in both directions. Reminders all-day due dates retain their source
calendar date when the local due timestamp still matches the source value.

The **Activity** tab shows LayerChart charts of task closures over time and
by area or project, plus counts, closures per week, days with closures and tasks
open now. Choose the last 30, 90 or 365 days, this year, last year, all time, or
a custom inclusive date range ending today or earlier. The date picker supports
calendar selection and typed dates; Apply commits the range and Cancel discards
it. Group by day, week or month. Select a bar or a period to inspect its tasks
and open their details.
Source, area, project, page, Reminders-list, tag and search filters apply to the statistics, independently
of the Tasks tab's status filter. Dates use the browser's timezone, weeks start
Monday, and periods with zero completions remain visible. Controls and selected
periods are saved in the URL, and charts update from the same live snapshots.

Activity counts tasks currently marked completed using Taskwarrior's `end`
date. Stacked bars distinguish `done`, `dropped`, `merged` and unspecified
outcomes. Outcome filtering scopes the closure charts while open-task counts
retain the other filters. Deleted tasks and invalid or missing closure dates are excluded.
Imports and bulk changes can create spikes; a snapshot cannot reconstruct
previous completions of reopened tasks or measure time spent. Weekly averages
include all calendar days in the selected range; open-task counts cover all
dates. The chart code loads only when opening Activity.

CLI changes appear automatically through a watcher on the Taskwarrior database
and WAL, debounced exports and Server-Sent Events. The server also re-exports
every 15 seconds; the browser refreshes every 30 seconds while visible and
when returning to the tab. Updates preserve selection and list position. Failed
exports retain the last successful snapshot and show a stale-data message.
Snapshot times describe local reads, not the freshness of upstream imports.

The server only exposes GET endpoints and runs `task export` with hooks,
recurrence generation and garbage collection disabled. It performs no task
edits, imports or synchronization. Taskwarrior status and imported source
status are displayed separately; records with several sources retain each
source link. Descriptions are rendered as text.

The frontend lives in `tools/taskwarrior-ui`; the existing
`home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl` builds it into
`scripts/taskwarrior_ui/` and installs the CLI. For development, run
`uv run taskwarrior-viewer`, then `pnpm dev` in `tools/taskwarrior-ui` (its `/api`
proxy uses port 8066). Validate with `pnpm check`, `pnpm test`, `pnpm build`,
and `uv run pytest -q tests/test_taskwarrior_viewer.py`. The backend tests use
isolated Taskwarrior data, never the live task database.

### Taskwarrior backups

With Taskwarrior 3, Git, jq, and sqlite3 installed, `chezmoi apply` enables hourly
backups through launchd on macOS or a systemd user timer on Linux. Run
`taskwarrior-backup` to back up immediately. Set `TASKWARRIOR_BACKUP_DIR` to
override the default `~/backups/taskwarrior` directory for a manual run.

The backup directory contains a Git repository tracking `tasks.json`, sorted by
UUID with derived `id` and `urgency` fields removed. Each run commits only when
the exported tasks change. `snapshots/` holds one complete SQLite backup per
calendar day, excluded from Git and retained indefinitely. Exports read a
consistent SQLite snapshot with hooks, recurrence generation, and garbage
collection disabled, leaving the live task database unchanged.

Backups stay local; no remote is configured and the script does not push.
You can later push the JSON repository to a private remote and include
`snapshots/` in an off-device backup separately.
The main `~/.taskrc` is already managed here; back up any additional configuration
includes and custom hooks separately.

On macOS, inspect `~/Library/Logs/taskwarrior-backup.log`. On Linux, use
`journalctl --user -u taskwarrior-backup.service` or
`systemctl --user list-timers taskwarrior-backup.timer`.

To test recovery from JSON without touching your live tasks:

```sh
mkdir -p /tmp/taskwarrior-restore
TASKDATA=/tmp/taskwarrior-restore task rc.hooks=off rc.recurrence=off import ~/backups/taskwarrior/tasks.json
TASKDATA=/tmp/taskwarrior-restore task count
```

For a full database restore, stop the backup job and all Taskwarrior clients,
move the current database **and its `-wal`/`-shm` files** aside, and copy the chosen
snapshot into the task data directory as `taskchampion.sqlite3`. Restart clients
only after the replacement is complete.

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
