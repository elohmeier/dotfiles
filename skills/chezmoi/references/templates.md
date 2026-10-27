# Templates and Machine Differences

## Upstream documentation

- [Templating](https://www.chezmoi.io/user-guide/templating/)
- [Manage machine-to-machine differences](https://www.chezmoi.io/user-guide/manage-machine-to-machine-differences/)
- [Template variables](https://www.chezmoi.io/reference/templates/variables/)
- [Template functions](https://www.chezmoi.io/reference/templates/functions/)
- [Init functions](https://www.chezmoi.io/reference/templates/init-functions/)

## Template basics

chezmoi templates use Go `text/template` syntax plus Sprig functions and chezmoi-specific functions.

A file is treated as a template if:

- its source filename ends in `.tmpl`, or
- it is under `.chezmoitemplates/`.

Create or convert templates:

```sh
chezmoi add --template ~/.gitconfig
chezmoi chattr +template ~/.zshrc
chezmoi edit ~/.zshrc
```

Test template snippets or files:

```sh
chezmoi execute-template '{{ .chezmoi.os }}/{{ .chezmoi.arch }}'
chezmoi cd
chezmoi execute-template < dot_zshrc.tmpl
chezmoi --skip-secrets cat ~/.zshrc
chezmoi --skip-secrets diff ~/.zshrc
```

## Template data

Inspect available data only when it is safe to expose the complete template-data object:

```sh
chezmoi data
```

When running through agent tools, do not capture `chezmoi data` output unless the data is known not to contain private values.

Data sources, with later values overriding earlier ones:

- `.chezmoi` variables populated by chezmoi, for example `.chezmoi.os`, `.chezmoi.arch`, `.chezmoi.hostname`, `.chezmoi.sourceDir`.
- `.chezmoidata.$FORMAT` files in the source state, read in alphabetical order. Formats include `json`, `jsonc`, `toml`, and `yaml`.
- `[data]` in the local config file, usually `~/.config/chezmoi/chezmoi.toml`.

Local config is good for private or machine-specific values:

```toml
[data]
email = "me@home.org"
work = false
```

If it contains private data, tell the user to keep the file mode private, for example `0600`.

## Machine-specific content

Use data and conditionals:

```gotemplate
[user]
    email = {{ .email | quote }}

{{- if eq .chezmoi.os "darwin" }}
# macOS-only content
{{- else if eq .chezmoi.os "linux" }}
# Linux-only content
{{- end }}
```

An empty rendered file removes the target. Use `empty_` if an empty file should exist.

## Conditional ignores

Use `.chezmoiignore` for coarse-grained machine differences:

```gotemplate
README.md
{{- if ne .chezmoi.hostname "work-laptop" }}
.work
{{- end }}
```

The logic is usually inverted: chezmoi installs everything by default, so ignore a path unless the condition should receive it.

Inspect ignored paths:

```sh
chezmoi ignored
```

## Shared template parts

Files under `.chezmoitemplates/` are reusable templates. Pass the current data explicitly when the included template needs `.chezmoi` or user variables:

```gotemplate
{{ template "part.tmpl" . }}
```

For different paths on different operating systems, put common contents in `.chezmoitemplates/file.conf`, create OS-specific target templates, then ignore the target path on other OSes.

## Include complete alternate files

For very different per-OS contents, keep alternates in source files and include one:

```gotemplate
{{- if eq .chezmoi.os "darwin" -}}
{{-   include ".bashrc_darwin" -}}
{{- else if eq .chezmoi.os "linux" -}}
{{-   include ".bashrc_linux" -}}
{{- end -}}
```

If alternates themselves need template evaluation, put them under `.chezmoitemplates/` and use `template`.

## Whitespace control

Use `{{-` and `-}}` to trim surrounding whitespace, especially when a template should output an exact file with no extra blank lines.

## Init templates

Init-time config templates use `.chezmoi.$FORMAT.tmpl` and prompt functions such as `promptStringOnce`, `promptBoolOnce`, and `promptChoiceOnce`.

Example:

```gotemplate
{{- $email := promptStringOnce . "email" "Email address" -}}

[data]
    email = {{ $email | quote }}
```
