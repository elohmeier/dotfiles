# Pi CLI And Resources

## CLI Package

The CLI package is `@earendil-works/pi-coding-agent`; the binary is `pi`.

Install:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Common modes:

```bash
pi                              # interactive TUI
pi "initial prompt"             # interactive with startup prompt
pi -p "summarize this repo"     # print final assistant text and exit
pi --mode json "prompt"         # JSONL events on stdout
pi --mode rpc                   # JSONL command/response protocol over stdin/stdout
pi --export session.jsonl out.html
```

Print mode also reads piped stdin:

```bash
cat README.md | pi -p "Summarize this"
```

File arguments use `@`:

```bash
pi @prompt.md @screenshot.png "Answer this"
```

## Models And Tools

Model selection:

```bash
pi --provider anthropic --model claude-sonnet-4-20250514
pi --model openai/gpt-4o
pi --model sonnet:high
pi --models "claude-*,gpt-4o"
pi --list-models
```

Tool controls:

```bash
pi --tools read,grep,find,ls -p "Review only"
pi --exclude-tools bash
pi --no-builtin-tools
pi --no-tools
```

Default active built-in tools are `read`, `bash`, `edit`, and `write`. Additional built-in tools exist for read-only workflows: `grep`, `find`, and `ls`.

## Config And Environment

Default user config directory is `~/.pi/agent`. Override with `PI_CODING_AGENT_DIR`.

Important environment variables:

- `PI_CODING_AGENT_DIR`: global config directory.
- `PI_CODING_AGENT_SESSION_DIR`: session storage override.
- `PI_PACKAGE_DIR`: package install directory override.
- `PI_OFFLINE=1`: disable startup network operations.
- `PI_SKIP_VERSION_CHECK=1`: skip update check.
- `PI_TELEMETRY=0`: opt out of install/update telemetry and attribution headers.
- `PI_CACHE_RETENTION=long`: request extended provider prompt cache where supported.
- `VISUAL` or `EDITOR`: external editor command.

Settings files:

- Global: `~/.pi/agent/settings.json`
- Project: `.pi/settings.json`

Project settings override global settings. Nested settings merge shallowly.

## Context And System Prompt Files

Pi loads `AGENTS.md` or `CLAUDE.md` from:

- `~/.pi/agent/`
- ancestor directories from cwd upward
- current directory

Disable context files with `--no-context-files` or `-nc`.

System prompt files:

- Replace default prompt: `.pi/SYSTEM.md` or `~/.pi/agent/SYSTEM.md`
- Append to default prompt: `.pi/APPEND_SYSTEM.md` or `~/.pi/agent/APPEND_SYSTEM.md`

CLI prompt flags:

```bash
pi --system-prompt "..."
pi --append-system-prompt "..."
pi --append-system-prompt ./prompt-extra.md
```

## Sessions

Sessions are append-only JSONL trees. Entries have `id` and `parentId`, so branches live in one file.

Common commands:

```bash
pi -c                         # continue most recent session
pi -r                         # select session
pi --session <path-or-id>
pi --fork <path-or-id>
pi --session-dir <dir>
pi --no-session
pi --name "task name"
```

Interactive commands:

- `/session`: show file, ID, stats.
- `/tree`: navigate branches in-place.
- `/fork`: create a new session from an earlier user message.
- `/clone`: duplicate the current active branch into a new session.
- `/compact [prompt]`: compact current context.
- `/new`, `/resume`, `/name`.

Source: `packages/coding-agent/src/core/session-manager.ts`, `docs/session-format.md`, `docs/sessions.md`.

## Skills

Skill discovery locations:

- `~/.pi/agent/skills/`
- `~/.agents/skills/`
- `.pi/skills/`
- `.agents/skills/` in cwd and ancestors
- package `skills/` resources
- settings `skills` array
- CLI `--skill <path>`

Skills register as `/skill:name` commands when skill commands are enabled.

Pi implements the Agent Skills standard leniently. Missing descriptions prevent loading; most other validation issues warn.

## Prompt Templates

Prompt templates are markdown files in:

- `~/.pi/agent/prompts/`
- `.pi/prompts/`
- package prompt resources
- settings `prompts` array
- CLI `--prompt-template <path>`

Arguments support `$1`, `$2`, `$@`, `$ARGUMENTS`, `${@:N}`, and `${@:N:L}` substitution. Source: `packages/coding-agent/src/core/prompt-templates.ts`.

## Extensions

Extensions are TypeScript modules discovered from:

- `~/.pi/agent/extensions/*.ts`
- `~/.pi/agent/extensions/*/index.ts`
- `.pi/extensions/*.ts`
- `.pi/extensions/*/index.ts`
- package extension resources
- settings `extensions` array
- CLI `-e` or `--extension`

Use `-e ./extension.ts` for quick testing. Use auto-discovered extension paths for `/reload`.

## Pi Packages

Pi packages bundle extensions, skills, prompts, and themes.

Install/manage:

```bash
pi install npm:@scope/pkg@1.2.3
pi install git:github.com/user/repo@v1
pi install ./local-package
pi remove npm:@scope/pkg
pi list
pi update
pi config
```

`-l` writes package settings to project `.pi/settings.json`; otherwise user settings are used.

Package manifest:

```json
{
  "name": "my-pi-package",
  "keywords": ["pi-package"],
  "pi": {
    "extensions": ["./extensions"],
    "skills": ["./skills"],
    "prompts": ["./prompts"],
    "themes": ["./themes"]
  }
}
```

Without a `pi` manifest, Pi auto-discovers conventional `extensions/`, `skills/`, `prompts/`, and `themes/` directories.
