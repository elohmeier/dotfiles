# Troubleshooting

## Upstream documentation

- [Troubleshooting](https://www.chezmoi.io/user-guide/frequently-asked-questions/troubleshooting/)
- [Usage FAQ](https://www.chezmoi.io/user-guide/frequently-asked-questions/usage/)
- [Command reference](https://www.chezmoi.io/reference/commands/)
- [Configuration warnings](https://www.chezmoi.io/reference/configuration-file/warnings/)

## First commands

Start with:

```sh
chezmoi doctor
chezmoi --skip-secrets status
chezmoi --skip-secrets diff
chezmoi --skip-secrets apply --dry-run --verbose
```

When investigating one target:

```sh
chezmoi source-path "$TARGET"
chezmoi --skip-secrets diff "$TARGET"
chezmoi --skip-secrets apply --dry-run --verbose "$TARGET"
```

Use `chezmoi cat "$TARGET"` only when the target is known not to contain secrets; it prints rendered contents.

## Determine what chezmoi thinks

List managed and ignored paths:

```sh
chezmoi managed
chezmoi ignored
chezmoi unmanaged
```

Map paths:

```sh
chezmoi source-path ~/.gitconfig
chezmoi target-path dot_gitconfig
```

Show config and template data:

```sh
chezmoi cat-config
chezmoi dump-config
chezmoi data # may expose private template data
```

## Template errors

Use:

```sh
chezmoi execute-template '{{ .chezmoi.hostname }}'
chezmoi cd
chezmoi execute-template < path/to/template.tmpl
chezmoi --skip-secrets cat "$TARGET"
```

Check common causes:

- missing `.tmpl` suffix on the source file
- wrong variable path, for example using `.data.email` when the value is available as `.email`
- `.chezmoitemplates` included without passing `.` as data
- unexpected whitespace because `{{-` or `-}}` was not used
- a rendered empty file causing target removal

## File does not appear or is not changing

Check:

- Is the file managed? `chezmoi managed | rg 'name'`
- Is it ignored? `chezmoi ignored | rg 'name'`
- Is the source filename correct? `chezmoi source-path $TARGET`
- Is it a `create_` file, which does not overwrite existing contents?
- Is it a `modify_` file, where the script/template output determines content?
- Is `.chezmoiignore` templated differently on this machine?

## Permissions are wrong

Use attributes:

```sh
chezmoi chattr +private ~/.ssh/config
chezmoi chattr +executable ~/.local/bin/tool
chezmoi chattr +readonly ~/.config/some/file
```

Then inspect:

```sh
chezmoi --skip-secrets diff
chezmoi --skip-secrets apply --dry-run --verbose
```

## Scripts did not run

Check:

- Script has `run_` prefix and a valid `#!` line.
- Rendered script is not empty or whitespace.
- `run_once_` may already have successful state for identical content.
- `run_onchange_` only runs when rendered content changes.
- Dry-run mode does not execute scripts.

State reset commands:

```sh
chezmoi state delete-bucket --bucket=entryState
chezmoi state delete-bucket --bucket=scriptState
```

Warn that resetting state can rerun scripts.

## Merge conflicts or local edits

Use:

```sh
chezmoi --skip-secrets diff "$TARGET"
chezmoi merge "$TARGET"
chezmoi re-add "$TARGET"
```

`merge` helps reconcile current target contents, source state, and rendered target contents. `re-add` refreshes source state from the current target; check the diff before committing.
