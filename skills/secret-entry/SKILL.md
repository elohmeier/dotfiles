---
name: secret-entry
description: Request a credential (token, password, API key) from the user without it passing through chat, tool calls, arguments, or logs. Use whenever a task needs a secret the user must supply or rotate, when checking whether a secret is already stored in a repository's SOPS env file (env.enc.yaml) or the pass password store, or when a repository's instructions mention `secret-entry` or `secrets:request`.
---

# Secret Entry

`secret-entry` is installed on PATH by the dotfiles (`elohmeier/dotfiles`,
`scripts/secret_entry.py`). It prompts with hidden input in the user's own
terminal and writes straight to encrypted storage. It never prints values.

## Backends

- **SOPS env file** (default): a flat `KEY: value` mapping. Default target is
  `env.enc.yaml` at the git root of the current directory; `--file PATH`
  selects another file (e.g. `clusters/production/.env.enc.yaml`). Encryption
  follows the nearest `.sops.yaml` above the file. Run from the repository so
  its mise-pinned `sops` is on PATH.
- **pass** (`--pass`): NAME is an entry such as `team/service/token` in
  `$PASSWORD_STORE_DIR`. pass encrypts to the store's GPG recipients and
  commits if the store is a git repository.
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

## Rules

- Never ask for secret values in chat, clarification tools, screenshots,
  command arguments, shell history, or plaintext files.
- Never print secrets: no `sops decrypt` of whole files, no `pass show` in an
  agent tool call, no `env` dumps.
- Consume a stored value inside the process that needs it (mise env loading,
  `sops decrypt` piped into a program, `pass show` captured by a program) and
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
