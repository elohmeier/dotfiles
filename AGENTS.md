# Enno's Dotfiles

Chezmoi-managed dotfiles repository and Python scripts collection.

- Store all chezmoi hook scripts under `home/.chezmoiscripts/` and reference that path in documentation or tooling updates.
- Platform-specific file exclusions go in `home/.chezmoiignore.tmpl`.
- Use `{{ lookPath "cmd" }}` for executable paths in templates.
- Find the shortest and most concise implementation possible. Avoid error handling and backwards compatibility if possible.

## Relevant Sources for your reference

- $HOME/repos/github.com/Textualize/rich
- $HOME/repos/github.com/ewels/rich-click
- $HOME/repos/github.com/folke/tokyonight.nvim
- $HOME/repos/github.com/pallets/click
- $HOME/repos/github.com/scottmckendry/cyberdream.nvim/extras/helix/cyberdream.toml
- $HOME/repos/github.com/twpayne/chezmoi
- $HOME/repos/github.com/twpayne/chezmoi/assets/chezmoi.io/docs/reference/index.md

## Theming

- Valid themes: `tokyonight_day`, `tokyonight_night`, `cyberdream_light`, `cyberdream`
- Use `{{ template "theme" . }}` in templates to get the validated theme name

## Chezmoi Scripts

Scripts in `home/.chezmoiscripts/` are organized by platform:

- `home/.chezmoiscripts/` — cross-platform scripts
- `home/.chezmoiscripts/darwin/` — macOS-only (ignored when not darwin)
- `home/.chezmoiscripts/linux/` — Linux-only (ignored when not linux)
- `home/.chezmoiscripts/wsl/` — WSL-only (ignored when `.isWSL` is false)

Platform filtering is handled by `home/.chezmoiignore.tmpl`.

## Agent Skills

Vendored skill files live in `home/dot_agents/skills/` (deploys to `~/.agents/skills/`). This is the canonical location, compatible with the [vercel-labs/skills](https://github.com/vercel-labs/skills) CLI layout.

Both `~/.claude/skills/` and `~/.codex/skills/` get chezmoi-templated symlinks pointing to `~/.agents/skills/<skill>`.

```
home/dot_agents/skills/              ← real files (source of truth)
  agent-browser/  msgvault/  opendataloader-pdf/  paperless-utils/

home/dot_claude/skills/              ← symlink_<skill>.tmpl → ~/.agents/skills/*
home/dot_codex/skills/               ← symlink_<skill>.tmpl → ~/.agents/skills/*
```

To add a new skill:

1. Add skill directory under `home/dot_agents/skills/<name>/SKILL.md`
2. Create `home/dot_claude/skills/symlink_<name>.tmpl` and `home/dot_codex/skills/symlink_<name>.tmpl` containing `{{ .chezmoi.homeDir }}/.agents/skills/<name>`

## Python

- Use click or rich-click by default for Python scripts that need CLI argument parsing.
- Add new CLIs by dropping a module in `scripts/`, pointing a `[project.scripts]` entry in `pyproject.toml` at its `main`, and let `home/.chezmoiscripts/run_onchange_install_uv_tools.sh.tmpl` install them via `uv`.
- Use `ruff format` for code formatting and `ruff check` for linting Python code.
- After editing Python files, always run: `ruff format <file> && ruff check <file> && ty check <file>`
