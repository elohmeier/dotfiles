---
name: secret-entry
description: Request a credential or generate a memorable passphrase without it passing through chat, tool calls, arguments, or logs. Use when supplying or rotating secrets, checking repository SOPS or pass/passage storage, or working with `secret-entry` or `secrets:request`.
---

# Secret Entry

`secret-entry` is installed on PATH by the dotfiles (`elohmeier/dotfiles`,
`scripts/secret_entry.py`). It prompts with hidden input in the user's own
terminal or generates a passphrase and writes straight to encrypted storage.
Values stay hidden unless the user explicitly requests `--generate --show`
in their own terminal.

## Backends

- **SOPS env file** (default): a flat `KEY: value` mapping. Default target is
  `env.enc.yaml` at the git root of the current directory; `--file PATH`
  selects another file (e.g. `clusters/production/.env.enc.yaml`). Encryption
  follows the nearest `.sops.yaml` above the file. Run from the repository so
  its mise-pinned `sops` is on PATH.
- **pass/passage** (`--pass`): NAME is an entry such as `team/service/token`
  in `$PASSAGE_DIR` or `$PASSWORD_STORE_DIR`. Once the store has an
  `.age-recipients` file (or `PASSAGE_DIR` is set), passage encrypts to its
  age recipients; otherwise pass encrypts to the GPG recipients. Both commit if
  the store is a git repository.
- **Host credential** (`--host`): use for personal CLI tokens such as
  `KANBOARD_TOKEN`. On macOS, stores in the user's Keychain under service
  `secret-entry`, with KEY as the account, using the native API. Keychain may
  ask the user to unlock or allow access. On Linux, seals with
  `systemd-creds --user` to this host's TPM2, host key and current user in
  `~/.local/share/secret-entry/KEY.cred`. Linux needs a usable TPM2 and access
  to the host key. `--tpm` explicitly selects Linux TPM storage and fails on
  macOS; recommend `--host` for portable setup. Unsupported TPM storage is
  rejected before the hidden prompt. If unavailable, use SOPS or pass and
  configure the consuming tool's token command.

Backend options (`--file`, `--pass`, `--host`, `--tpm`) are mutually exclusive.

## Handoff

1. Name the key or entry, its purpose, and the minimum permissions it needs.
2. Check whether it already exists; no decryption output is shown:

   ```sh
   secret-entry status KEY            # exit 0 present, 1 missing, 2 error
   secret-entry status --pass team/service/token
   secret-entry status --host KEY
   ```

   With `--host`, exit 2 means storage is unavailable or failed; resolve that
   before asking the user to enter a credential. Exit 1 means the selected
   store is ready but the value is missing.

3. If it must be added or rotated, give the user the command to run **in
   their own terminal window**. Claude Code's `! <command>` prefix has no
   terminal, so the hidden prompt refuses to run there. Never run the prompt
   in an agent-owned terminal:

   ```sh
   secret-entry request KEY
   secret-entry request --file clusters/production/.env.enc.yaml TF_VAR_token
   secret-entry request --pass team/service/token
   secret-entry request --host KEY
   ```

   Running `request` again replaces the value (rotation).

4. After the user says it was saved, verify with `status` and continue.

If the repository defines its own wrapper task (for example
`mise run secrets:request -- KEY` that also delivers values into Kubernetes
Secrets), use that wrapper; its own instructions take precedence.

## Store a value a program issues

When a command issues the credential (a CLI that creates an API token), pipe
it into `request --stdin`, so it goes from the program into encrypted storage
without being shown:

```sh
some-cli token create ... | secret-entry request --stdin KEY
```

`--stdin` reads exactly one value from a pipe and drops one trailing line
ending. It refuses a terminal, an empty or multiline value, and `--generate`,
and prints only status. It works with every backend. Use it only for a value
a program produces; a value the user holds still goes through the hidden
prompt in their own terminal. Never build the pipe from a value you can see
(`echo`, a here-string, a file you wrote): that passes the secret through a
tool call.

## Generate a memorable password

Use `request --generate` when a new password is needed; tokens issued by a
service still need the hidden prompt, or `--stdin` when a program hands them over. Generation uses Python's `secrets`
module and the bundled EFF short word list #1, with hyphens between words.
It works with every backend and does not need a network connection.

```sh
secret-entry request --generate --pass accounts/example
secret-entry request --generate --words 6 --show --pass accounts/example
```

The default is eight words (82.7 bits of entropy, about 43 characters).
`--words` accepts six or more; six words give 62.0 bits, about 32 characters.
`--words` and `--show` require `--generate`. Running again replaces the
stored value, just like prompted entry; storage does not change the password
at the service that will use it.

Without `--show`, generation prints only status and can run without a terminal
when the user has authorized creating or rotating the stored password.
For memorization, give the user the `--show` command to run in their own terminal.
It refuses redirected input or output and reveals the phrase only after a
successful save. The phrase remains in terminal scrollback. Never run `--show`
in an agent-owned terminal or capture its output.

## Rules

- Never ask for secret values in chat, clarification tools, screenshots,
  command arguments, shell history, or plaintext files.
- Never print secrets: no `sops decrypt` of whole files, no `pass show`/`passage show`
  in an agent tool call, no `env` dumps. The explicit `--generate --show`
  workflow above reveals only to the user in their own terminal.
- Consume a stored value inside the process that needs it (mise env loading,
  `sops decrypt` piped into a program, `pass show`/`passage show`
  captured by a program) and
  send it directly to the intended API. Keep values out of `curl` or CLI
  arguments and withhold request bodies and credentials from logs.
- `secret-entry read KEY` prints a host credential for a tool to consume
  (`FOO_TOKEN_COMMAND='secret-entry read FOO_TOKEN'`, or `host_secret()` in
  dotfiles Python). It refuses a terminal; never run it on its own in an agent
  tool call. To check that a stored token is the intended one, compare hashes
  (`sha256sum`), never values.
- `secret-entry` stores only; it does not deploy, publish, or commit SOPS
  files. Review and commit the encrypted file when persistence is intended.
- Values must be nonempty single-line text. Multiline material (certificates,
  structured Kubernetes Secrets) uses the repository's own SOPS workflow.
