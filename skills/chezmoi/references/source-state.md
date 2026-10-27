# Source State, Attributes, and Special Files

## Upstream documentation

- [Concepts](https://www.chezmoi.io/reference/concepts/)
- [Source state attributes](https://www.chezmoi.io/reference/source-state-attributes/)
- [Target types](https://www.chezmoi.io/reference/target-types/)
- [Manage different types of file](https://www.chezmoi.io/user-guide/manage-different-types-of-file/)
- [Special files](https://www.chezmoi.io/reference/special-files/)

## Source state basics

The source directory stores desired state using only regular files and directories. Names encode target paths and attributes.

Common mappings:

| Source path                      | Target path or action                                  |
| -------------------------------- | ------------------------------------------------------ |
| `dot_bashrc`                     | `~/.bashrc`                                            |
| `dot_gitconfig.tmpl`             | render template to `~/.gitconfig`                      |
| `private_dot_ssh/config`         | `~/.ssh/config` with private permissions               |
| `executable_dot_local/bin/tool`  | executable target file                                 |
| `symlink_dot_config/app/current` | symlink target whose contents are the link destination |
| `run_once_install.sh`            | script run once for a unique script content            |

Use commands rather than manually deriving names when possible:

```sh
chezmoi source-path ~/.gitconfig
chezmoi target-path dot_gitconfig
chezmoi chattr +private ~/.ssh/config
```

## Attribute order

Attribute prefixes must be in the expected order for each target type. If unsure, use `chezmoi chattr` or inspect the upstream [source state attributes](https://www.chezmoi.io/reference/source-state-attributes/) reference.

Important prefixes:

| Prefix                   | Meaning                                                |
| ------------------------ | ------------------------------------------------------ |
| `dot_`                   | leading dot in target name                             |
| `private_`               | remove group/world permissions                         |
| `readonly_`              | remove write permissions                               |
| `executable_`            | set executable bits                                    |
| `empty_`                 | keep empty file instead of removing it                 |
| `create_`                | create if missing, leave existing contents unchanged   |
| `modify_`                | script/template transforms current target contents     |
| `symlink_`               | create symbolic link                                   |
| `run_`                   | execute script                                         |
| `once_`                  | script runs only for content not previously successful |
| `onchange_`              | script runs when rendered contents change              |
| `before_` / `after_`     | script runs before or after file updates               |
| `remove_`                | remove target entry                                    |
| `exact_`                 | remove unmanaged entries under that directory          |
| `encrypted_`             | encrypted source file                                  |
| `literal_` or `.literal` | stop parsing attributes                                |

`.tmpl` means render the source file as a template. Encrypted age/GPG suffixes such as `.age` or `.asc` are stripped after decryption.

## Target types

Files: regular source files. Empty rendered contents remove the target unless `empty_` is present.

Create files: `create_` writes initial contents only if missing. It can manage permissions without overwriting existing contents.

Modify files: `modify_` scripts receive current target contents on stdin and write new contents to stdout. Modify templates contain `chezmoi:modify-template`; the current contents are available as `.chezmoi.stdin`. Modify templates must not have `.tmpl`.

Directories: source directories create target directories. `exact_` removes target entries not present in source; treat this as destructive.

Symlinks: `symlink_` source file contents are the link destination. A trailing newline is stripped. Empty link targets remove the symlink target.

Scripts: `run_` source files execute during apply. See `scripts.md`.

## Special files

`.chezmoiignore`: template of ignore patterns. Use it to exclude files entirely or conditionally by machine. Use `chezmoi ignored` to inspect results.

`.chezmoiremove`: template of patterns to remove from the destination. Always dry-run first:

```sh
chezmoi --skip-secrets apply --dry-run --verbose
```

`.chezmoidata.$FORMAT`: user data loaded into templates. Supported formats include JSON, JSONC, TOML, and YAML.

`.chezmoitemplates/`: reusable templates loadable from other templates with `template`.

`.chezmoi.$FORMAT.tmpl`: init-time local config template.

`.chezmoiexternal.$FORMAT`: declares external files downloaded into the source state.

`.chezmoiroot`: marks a root inside a larger git working tree.

`.chezmoiversion`: version constraint file.

## Managing partial files

Prefer whole-file templates when possible. Use `modify_` when another program owns parts of a file or when preserving user-managed sections matters.

Example modify template:

```gotemplate
{{- /* chezmoi:modify-template */ -}}
{{ fromJson .chezmoi.stdin | setValueAtPath "key.nestedKey" "value" | toPrettyJson }}
```

## Externally modified config files

For apps that constantly rewrite config files, consider a symlink from the target path back to a source-controlled file, plus `.chezmoiignore` for the backing source file so chezmoi does not also create it in the home directory.
