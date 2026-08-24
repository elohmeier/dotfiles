# Secrets, Password Managers, and Encryption

## Upstream documentation

- [Password managers](https://www.chezmoi.io/user-guide/password-managers/)
- [Encryption](https://www.chezmoi.io/user-guide/encryption/)
- [age encryption](https://www.chezmoi.io/user-guide/encryption/age/)
- [GPG encryption](https://www.chezmoi.io/user-guide/encryption/gpg/)
- [Encryption FAQ](https://www.chezmoi.io/user-guide/frequently-asked-questions/encryption/)

## Preference order

1. Password manager template functions for individual secret values or whole documents.
2. Encrypted source files with `chezmoi add --encrypt` for files that must live in the repo.
3. Local config data in `~/.config/chezmoi/chezmoi.toml` for machine-specific private values, kept with private permissions.

Avoid plaintext secrets in the source repo.

## Password managers

chezmoi provides template functions for many password managers. The exact function depends on the provider; inspect the upstream [password-manager guide](https://www.chezmoi.io/user-guide/password-managers/) and [template-function reference](https://www.chezmoi.io/reference/templates/) when advising on a provider.

Example 1Password token in a shell template:

```gotemplate
export CF_API_TOKEN='{{ onepasswordRead "op://Personal/cloudflare-api-token/password" }}'
```

For complete secret files stored in password managers, use the provider's document/file function when available, for example 1Password documents.

Warn that rendered target files may contain secrets even if the repo does not.

When running commands through agent tools, do not capture decrypted or rendered secret contents. Start previews with:

```sh
chezmoi --skip-secrets status
chezmoi --skip-secrets diff
chezmoi --skip-secrets apply --dry-run --verbose
```

This omits secret-bearing targets. If the user authorizes applying one, apply only that target without `--verbose` and do not read its rendered contents back into tool output.

## Encryption overview

chezmoi supports age, GPG, git-crypt, and transcrypt. Encrypted files use the `encrypted_` attribute in source state and are decrypted when needed for commands such as `apply`, `diff`, `status`, and `edit`.

Add an encrypted file:

```sh
chezmoi add --encrypt ~/.ssh/id_rsa
```

Edit an encrypted file:

```sh
chezmoi edit ~/.ssh/id_rsa
```

chezmoi decrypts before editing and re-encrypts after editing.

## age

Generate a key:

```sh
chezmoi age-keygen --output=$HOME/key.txt
```

Configure age:

```toml
encryption = "age"

[age]
identity = "/home/user/key.txt"
recipient = "age1..."
```

Multiple identities and recipients are supported:

```toml
encryption = "age"

[age]
identities = ["/home/user/key1.txt", "/home/user/key2.txt"]
recipients = ["recipient1", "recipient2"]
```

Keep `encryption = "age"` at top level, before sections.

The built-in age support is used if the `age` command is unavailable, but it does not support passphrases, symmetric encryption, or SSH keys. If the user needs those features, require the external age command and inspect current docs.

## Local private data

Machine-specific data can live in local config:

```toml
[data]
email = "firstname.lastname@company.com"
apiHost = "internal.example.com"
```

If private:

```sh
chmod 600 ~/.config/chezmoi/chezmoi.toml
```

Use templates to consume this data:

```gotemplate
token = {{ .token | quote }}
```

For highly sensitive values, prefer a password manager over local config.

## Public repository warnings

- `git autoPush` can publish mistakes quickly.
- `chezmoi diff` and verbose apply may print rendered secrets.
- Scripts can leak secrets through shell tracing, logs, or package manager commands.
- Encrypted source files protect the repo, not the generated target files.
