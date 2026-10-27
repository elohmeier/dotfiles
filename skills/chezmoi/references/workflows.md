# chezmoi Workflows

## Upstream documentation

- [Quick start](https://www.chezmoi.io/quick-start/)
- [Command overview](https://www.chezmoi.io/user-guide/command-overview/)
- [Daily operations](https://www.chezmoi.io/user-guide/daily-operations/)
- [Setup](https://www.chezmoi.io/user-guide/setup/)

## Mental model

- Destination directory: usually `~`, where target files live.
- Source directory: usually `~/.local/share/chezmoi`, usually a git working tree containing desired state.
- Config file: usually `~/.config/chezmoi/chezmoi.toml`, containing machine-specific data.
- `chezmoi apply` computes target state from source state, config, and current destination state, then updates the destination.

## First machine

```sh
chezmoi init
chezmoi add ~/.bashrc
chezmoi edit ~/.bashrc
chezmoi --skip-secrets diff
chezmoi --skip-secrets apply --dry-run --verbose
chezmoi apply
chezmoi cd
git add .
git commit -m "Initial commit"
git remote add origin git@github.com:$GITHUB_USERNAME/dotfiles.git
git branch -M main
git push -u origin main
exit
```

Use HTTPS or SSH remotes according to the user's auth setup. Private GitHub repositories normally need SSH or a personal access token for HTTPS git auth.

## New machine

Preview-first flow:

```sh
chezmoi init git@github.com:$GITHUB_USERNAME/dotfiles.git
chezmoi --skip-secrets diff
chezmoi --skip-secrets apply --dry-run --verbose
chezmoi apply
```

One-command flow:

```sh
chezmoi init --apply git@github.com:$GITHUB_USERNAME/dotfiles.git
```

GitHub shorthand works when the repo is `github.com/$GITHUB_USERNAME/dotfiles`:

```sh
chezmoi init --apply $GITHUB_USERNAME
```

Transitory environments can use one-shot mode:

```sh
sh -c "$(curl -fsLS https://get.chezmoi.io)" -- init --one-shot $GITHUB_USERNAME
```

## Daily operations

Edit source for a target:

```sh
chezmoi edit "$TARGET"
chezmoi --skip-secrets diff "$TARGET"
chezmoi apply "$TARGET"
```

Edit and apply after editor exits:

```sh
chezmoi edit --apply "$TARGET"
```

Edit and apply on save:

```sh
chezmoi edit --watch "$TARGET"
```

Pull and apply:

```sh
chezmoi update
```

Pull and preview before applying:

```sh
chezmoi git pull -- --autostash --rebase
chezmoi --skip-secrets diff
chezmoi --skip-secrets apply --dry-run --verbose
chezmoi apply
```

## Git integration

The source directory is a git repo. Use:

```sh
chezmoi cd
git status
git add .
git commit -m "Update dotfiles"
git push
exit
```

Auto-commit and auto-push can be enabled in the local config:

```toml
[git]
autoCommit = true
autoPush = true
```

Warn users that auto-push can publish accidentally added plaintext secrets, especially in public repos.

## Initial config generation

If the source repo contains `.chezmoi.$FORMAT.tmpl` where `$FORMAT` is `json`, `jsonc`, `toml`, or `yaml`, `chezmoi init` can generate the local config file.

Example `.chezmoi.toml.tmpl`:

```gotemplate
{{- $email := promptStringOnce . "email" "Email address" -}}

[data]
    email = {{ $email | quote }}
```

Test an init template:

```sh
chezmoi execute-template --init --promptString "Email address=me@home.org" < ~/.local/share/chezmoi/.chezmoi.toml.tmpl
```

Re-run `chezmoi init` to regenerate config after template changes.
