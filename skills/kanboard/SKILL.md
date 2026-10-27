---
name: kanboard
description: Inspect and change the team's Kanboard (boards Convexio, Sales, Haushalt) with the `kanboard` CLI - list and search tasks, show a board, create or update tasks, move, assign, close, comment, add subtasks and links. Use when the user mentions Kanboard, the board, a task or card number like #118, the backlog, or asks to put something on the board.
---

# Kanboard

`kanboard` is installed on PATH by the dotfiles (`elohmeier/dotfiles`,
`scripts/kanboard.py`). It talks to Kanboard's JSON-RPC API over the tailnet
(`https://kanboard-api.pug-coho.ts.net/jsonrpc.php`) as the user's own
account, so every change is attributed to them. The web UI is
`https://violet-ridge-anchor.hf40.de`; every task in the output has its `url`.

## Credential

A personal API token (Kanboard: avatar > My profile > API > generate), not the
global application token under Settings > API. The CLI reads `KANBOARD_TOKEN`,
then `KANBOARD_TOKEN_COMMAND`, then the host credential from
`secret-entry request --host KANBOARD_TOKEN` (macOS Keychain or Linux TPM2;
see the `secret-entry` skill). Check `secret-entry status --host KANBOARD_TOKEN`
before handing the user that request command. If host storage is unavailable,
use `KANBOARD_TOKEN_COMMAND` with an existing password manager, for example
`export KANBOARD_TOKEN_COMMAND='pass show kanboard/token'` after saving with
`secret-entry request --pass kanboard/token`. Never suggest `--tpm` on macOS.

## Output

JSON on stdout by default; `-o jsonl` streams lists, `-o table` is for people.
Errors are `{"error": "..."}` on stderr with exit 3 (not found, including an
unknown column, swimlane, tag or user name) or 4 (API refused). Tasks carry
names and IDs: `column`, `swimlane`, `assignee`, `tags`, ISO dates, `url`.

## Commands

```sh
kanboard whoami | projects
kanboard board CONVEXIO                      # columns, swimlanes, open counts
kanboard columns|swimlanes|members|tags CONVEXIO
kanboard tasks CONVEXIO --column Backlog --swimlane Product --assignee enno --tag bug
kanboard tasks CONVEXIO 'due:<2026-12-01' --status all --full   # Kanboard search syntax
kanboard task show 118 --comments --subtasks --links
kanboard task create CONVEXIO --title '...' --swimlane Product --description - < body.md
kanboard task ensure CONVEXIO --reference forgejo:billing#50 --title '...'
kanboard task update 118 --assignee me --tag ux --due 2026-11-30
kanboard task move 118 --column 'Work in progress'
kanboard task assign 118 none | close 118 | reopen 118
kanboard comment add 118 - < note.md     |  comment list 118
kanboard subtask add 118 'Title'         |  subtask done 42
kanboard link add 118 https://... --title '...'
kanboard activity CONVEXIO --since 7d
kanboard call getBoard '{"project_id": 1}'   # any API procedure
```

Projects take an identifier (`CONVEXIO`), name or ID; names are
case-insensitive. Long text takes `-` (stdin) or `@file`.

## Conventions

- The boards' columns, swimlanes, tags and members are configured in the ops
  repository (`enno/ops`, `kanboard/`); the CLI never creates tags. Ask before
  proposing a new tag or column, and change it there, not in the UI.
- Convexio tasks: short German titles; Backlog for new work; swimlanes Support,
  Product, Sales/Marketing, Operations. Leave tasks unassigned unless asked.
- Use `task ensure --reference <system>:<id>` (for example
  `forgejo:billing#50`) when a task mirrors an issue or PR, so reruns do not
  create duplicates.
- The board is shared with the team: confirm before closing, moving or
  reassigning other people's tasks, and do not create test tasks there.
