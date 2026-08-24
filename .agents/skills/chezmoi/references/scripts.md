# Scripts

## Upstream documentation

- [Use scripts to perform actions](https://www.chezmoi.io/user-guide/use-scripts-to-perform-actions/)
- [Target types](https://www.chezmoi.io/reference/target-types/)
- [Interpreters](https://www.chezmoi.io/reference/configuration-file/interpreters/)

## When to use scripts

Use scripts for actions outside file state, such as package installs, service reloads, migrations, or importing desktop settings. Prefer declarative files, templates, symlinks, `create_`, `modify_`, and permission attributes for file contents and metadata.

All scripts should be idempotent. This applies even to `run_once_` and `run_onchange_` scripts, because users may clear state, edit scripts, or re-run apply in unusual environments.

## Script kinds

| Prefix                                    | Behavior                                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------- |
| `run_`                                    | executes every `chezmoi apply`                                                              |
| `run_once_`                               | executes once for each unique rendered content hash, after successful run state is recorded |
| `run_onchange_`                           | executes when rendered script contents change                                               |
| `run_before_` / `run_after_`              | executes before or after file updates                                                       |
| `run_once_before_`, `run_onchange_after_` | combine timing and state semantics                                                          |

Scripts execute in ASCII order by target name. Without before/after, they are interleaved with file updates according to target order.

## Creating scripts

Scripts are source files, usually created manually:

```sh
chezmoi cd
$EDITOR run_onchange_install-packages.sh
```

Scripts do not need the executable bit in the source state, but they must include a `#!` line or be an executable binary because chezmoi writes them to a temporary executable file and runs them.

Use `.tmpl` to conditionally generate script contents. If a rendered script is empty or whitespace only, it does not run.

Example package install script:

```gotemplate
{{ if eq .chezmoi.os "linux" -}}
#!/bin/sh
sudo apt install ripgrep
{{ else if eq .chezmoi.os "darwin" -}}
#!/bin/sh
brew install ripgrep
{{ end -}}
```

## Script location

Scripts in the source tree can correspond to a working directory in the destination tree. If the equivalent destination location does not exist, chezmoi walks up to the first existing parent directory.

Use root `.chezmoiscripts/` for scripts that should not create a corresponding target directory.

## Environment

chezmoi sets `CHEZMOI=1` and common `CHEZMOI_*` variables corresponding to template data, such as OS and architecture.

Add custom environment variables in local config:

```toml
[scriptEnv]
MY_VAR = "my_value"
```

## Trigger on another file changing

Include a checksum of another source file in a `run_onchange_` script:

```gotemplate
#!/bin/bash

# dconf.ini hash: {{ include "dconf.ini" | sha256sum }}
dconf load / < {{ joinPath .chezmoi.sourceDir "dconf.ini" | quote }}
```

Add the referenced source-only file to `.chezmoiignore` if it should not become a target in the home directory.

## Diff and dry-run behavior

Dry-run mode does not execute scripts. Verbose mode prints script contents before execution. `chezmoi diff` can print scripts that would run. When running through agent tools, add `--skip-secrets` unless the scripts are known not to render secrets.

Hide scripts from diff/status output:

```toml
[diff]
exclude = ["scripts"]

[status]
exclude = ["scripts"]
```

## Clearing script state

Clear `run_onchange_` state:

```sh
chezmoi state delete-bucket --bucket=entryState
```

Clear `run_once_` state:

```sh
chezmoi state delete-bucket --bucket=scriptState
```

Mention that clearing state can cause scripts to run again.
