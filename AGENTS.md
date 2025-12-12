# Enno's Dotfiles

Chezmoi-managed dotfiles repository and Python scripts collection.

- Store all chezmoi hook scripts under `home/.chezmoiscripts/` and reference that path in documentation or tooling updates.
- Platform-specific file exclusions go in `home/.chezmoiignore.tmpl`.
- Find the shortest and most concise implementation possible. Avoid error handling and backwards compatibility if possible.

## External Sources

- Chezmoi source code: `$HOME/repos/github.com/twpayne/chezmoi`
- Chezmoi reference: `$HOME/repos/github.com/twpayne/chezmoi/assets/chezmoi.io/docs/reference/index.md`
- Click source code: `$HOME/repos/github.com/pallets/click`
- Rich source code: `$HOME/repos/github.com/Textualize/rich`
- Rich-click source code: `$HOME/repos/github.com/ewels/rich-click`

## Python

- Use click or rich-click by default for Python scripts that need CLI argument parsing.
- Add new CLIs by dropping a module in `scripts/`, pointing a `[project.scripts]` entry in `pyproject.toml` at its `main`, and let `home/.chezmoiscripts/run_onchange-install_uv_tools.sh.tmpl` install them via `uv`.
- Use `ruff format` for code formatting and `ruff check` for linting Python code.
