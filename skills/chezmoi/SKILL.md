---
name: chezmoi
description: Use when helping users set up, maintain, troubleshoot, or improve chezmoi dotfiles repositories, including init/apply/update workflows, source-state filenames and attributes, templates, machine-specific config, scripts, secrets, encryption, password managers, git workflows, and safe validation commands.
---

# chezmoi

Use this skill for user-facing chezmoi dotfiles help: designing a repo, adding or editing managed files, converting files to templates, handling machine-specific differences, managing scripts or secrets, debugging apply/diff/status behavior, and giving safe command sequences.

For exact command flags, inspect the user's installed version with `chezmoi <command> --help`. For broader behavior and edge cases, consult the relevant reference in this skill and the [official chezmoi documentation](https://www.chezmoi.io/).

## Default Workflow

1. Identify whether the user is working in the destination directory, a chezmoi source directory, or an upstream chezmoi code checkout. Do not infer this from the skill's installation path.
2. Prefer secret-safe inspection and dry-run commands before mutating a destination directory:
   ```sh
   chezmoi doctor
   chezmoi --skip-secrets status
   chezmoi --skip-secrets diff
   chezmoi --skip-secrets apply --dry-run --verbose
   ```
3. For edits to managed dotfiles, prefer source-state edits through chezmoi:
   ```sh
   chezmoi edit "$TARGET"
   chezmoi --skip-secrets diff "$TARGET"
   chezmoi apply "$TARGET"
   ```
4. For repo changes, use `chezmoi cd` or `chezmoi source-path` to locate the source directory, then use normal git commands.
5. When a task involves secrets, private machine data, package installs, or scripts, explicitly call out side effects and validation commands.

## Common Tasks

- **First setup or new machine**: Read [workflows.md](references/workflows.md). Use `chezmoi init`, `chezmoi init --apply`, or `chezmoi update` depending on whether a source repo already exists.
- **Daily editing**: Use `chezmoi edit`, `chezmoi edit --apply`, `chezmoi status`, `chezmoi diff`, `chezmoi apply`, and `chezmoi update`.
- **Source filenames and attributes**: Read [source-state.md](references/source-state.md) before advising on names such as `dot_`, `private_`, `executable_`, `symlink_`, `run_once_`, `modify_`, or `.tmpl`.
- **Machine-specific config**: Read [templates.md](references/templates.md). Prefer templates plus local config data over duplicating entire files.
- **Scripts and package installation**: Read [scripts.md](references/scripts.md). Scripts should be idempotent and tested with dry-run/diff when possible.
- **Secrets, password managers, and encryption**: Read [secrets.md](references/secrets.md). Prefer password-manager template functions or encrypted source files over plaintext secrets.
- **Unexpected behavior**: Read [troubleshooting.md](references/troubleshooting.md). Start with `chezmoi doctor`, then inspect target/source paths and render target content only when it is known not to contain secrets.

## Safety Rules

- Do not suggest `chezmoi apply` broadly until the user has seen `chezmoi --skip-secrets diff` or `chezmoi --skip-secrets apply --dry-run --verbose`, unless they explicitly ask for a direct apply flow.
- When running commands through agent tools, use `--skip-secrets` for `status`, `diff`, `cat`, `data`, `execute-template`, and dry runs unless the selected input is known not to contain secrets. Do not capture decrypted files, rendered secrets, or full private template data in tool output.
- `--skip-secrets` can omit secret-bearing targets from the preview. If the user authorizes applying them, apply only the intended target without verbose output and explain that it was excluded from the preview.
- Treat `exact_`, `.chezmoiremove`, `remove_`, `purge`, and `destroy` as destructive. Explain what they can delete and include a dry-run command.
- Never put tokens, private keys, passwords, or personal machine data in the source repo as plaintext. Use a password manager, encrypted files, or local config with private permissions.
- Do not recommend `run_` scripts for declarative file state if a normal file, template, symlink, `create_`, `modify_`, or permission attribute solves the problem.
- Be precise about source path vs target path. Example: `dot_gitconfig.tmpl` in the source directory renders to `~/.gitconfig`.

## High-Signal Commands

```sh
chezmoi doctor                         # diagnose common problems
chezmoi source-path [TARGET]           # show source path for target or source dir
chezmoi target-path SOURCE             # show target path for source file
chezmoi managed                        # list managed target paths
chezmoi unmanaged                      # list unmanaged files
chezmoi ignored                        # list ignored paths
chezmoi --skip-secrets cat TARGET      # print a non-secret rendered target
chezmoi execute-template '{{ .chezmoi.os }}'
chezmoi data                           # may expose private template data
chezmoi chattr +template TARGET        # make managed target a template
chezmoi chattr +private TARGET         # mark target private
chezmoi re-add TARGET                  # refresh source state from target
chezmoi merge TARGET                   # three-way merge local/source/rendered
```

## Reference Map

- [workflows.md](references/workflows.md): setup, new machines, daily operations, git, config generation.
- [source-state.md](references/source-state.md): source-state model, attributes, target types, special files.
- [templates.md](references/templates.md): template data, `.chezmoidata`, `.chezmoitemplates`, testing, machine differences.
- [scripts.md](references/scripts.md): `run_`, `run_once_`, `run_onchange_`, before/after, script environment, package installs.
- [secrets.md](references/secrets.md): password managers, age/GPG encryption, local-private data, public repo safety.
- [troubleshooting.md](references/troubleshooting.md): diagnosis patterns and common fixes.
