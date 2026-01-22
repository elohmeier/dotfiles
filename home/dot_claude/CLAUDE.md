# Global Claude Configuration

## Available CLI Tools

These tools are installed and available for use:

**Core:** `bat`, `eza`, `fd`, `fzf`, `just`, `rg` (ripgrep), `sops`, `uv`, `zoxide`

**Git:** `git`, `git-delta`, `git-lfs`, `gh`

**Languages/Runtimes:** `go`, `bun`, `pnpm`

**Formatters/Linters:** `dprint`, `shellcheck`, `shfmt`, `stylua`, `taplo`, `typstyle`

**Infrastructure:** `helm`, `opentofu`, `minio-mc`

**Other:** `entr`, `go-jsonnet`, `jb` (jsonnet-bundler), `make`, `rsync`, `typst`, `uu-timeout` (timeout/gtimeout), `watch`, `yq`

## Repository Layout

Repositories are organized under `$HOME/repos` using the pattern:

```
$HOME/repos/<host>/<owner>/<repo>
```

Examples:

- `$HOME/repos/github.com/anthropics/claude-code`
- `$HOME/repos/gitlab.com/myorg/myproject`

## The `h` Tool

The `h` command (`$HOME/.local/bin/h`) clones and navigates to repositories:

```bash
h anthropics/claude-code  # Clone/cd to github.com/anthropics/claude-code
h claude-code             # Search and cd to repo by name (case-insensitive)
h https://github.com/...  # Clone from any URL
```

Use `h` to fetch reference implementations. The CLAUDE.md in this dotfiles repo lists useful repos under "Relevant Sources".
