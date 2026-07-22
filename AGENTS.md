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
- Use `includeTemplate "theme" .` when the validated name is needed in an expression

## Chezmoi Scripts

Scripts in `home/.chezmoiscripts/` are organized by platform:

- `home/.chezmoiscripts/` — cross-platform scripts
- `home/.chezmoiscripts/darwin/` — macOS-only (ignored when not darwin)
- `home/.chezmoiscripts/linux/` — Linux-only (ignored when not linux)
- `home/.chezmoiscripts/wsl/` — WSL-only (ignored when `.isWSL` is false)

Platform filtering is handled by `home/.chezmoiignore.tmpl`.

## Agent Skills

Agent skills live in the dedicated [elohmeier/skills](https://github.com/elohmeier/skills) repository and are installed globally for Claude Code and Codex with `djust install-skills`. Do not vendor skills or agent-specific skill symlinks in this repository.

## Python

- Use click or rich-click by default for Python scripts that need CLI argument parsing.
- Add new CLIs by dropping a module in `scripts/`, pointing a `[project.scripts]` entry in `pyproject.toml` at its `main`, and let `home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl` install them via `uv`.
- Use `uv run ruff format` for code formatting and `uv run ruff check` for linting Python code (`ruff` and `ty` are dev dependencies).
- After editing Python files, always run: `uv run ruff format <file> && uv run ruff check <file> && uv run ty check <file>`
