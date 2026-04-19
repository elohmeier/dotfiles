---
name: msgvault
description: Find emails in the msgvault archive based on the user's description.
allowed-tools: Bash(msgvault:*)
---

## Instructions

You are helping the user find emails in their msgvault email archive. Translate their natural language request into the appropriate `msgvault` CLI commands, run them, and present the results.

Always use `--json` output for programmatic parsing, then present results in a readable format.

### Argument: $ARGUMENTS

The user's description of what emails they're looking for.

## Available Commands

### Search (primary tool)

```bash
msgvault search <query> [--limit N] [--offset N] [--json] [--account EMAIL]
```

Gmail-like query syntax:

- `from:EMAIL` - sender email
- `to:EMAIL` - recipient email
- `cc:EMAIL` / `bcc:EMAIL` - CC/BCC recipients
- `subject:TEXT` - subject text
- `label:NAME` (or `l:NAME`) - Gmail label
- `has:attachment` - messages with attachments
- `before:YYYY-MM-DD` / `after:YYYY-MM-DD` - date range
- `older_than:7d` / `newer_than:30d` - relative dates (d/w/m/y)
- `larger:5M` / `smaller:100K` - size filters
- Bare words and `"quoted phrases"` for full-text search

### Show Message Detail

```bash
msgvault show-message <id> [--json]
```

Shows full message content including body, headers, attachments.

### Aggregation Commands

```bash
msgvault list-senders [--limit N] [--after DATE] [--before DATE] [--json]
msgvault list-domains [--limit N] [--after DATE] [--before DATE] [--json]
msgvault list-labels  [--limit N] [--after DATE] [--before DATE] [--json]
```

### Stats

```bash
msgvault stats
```

## Workflow

1. Parse the user's natural language request into the best query
2. Run `msgvault search` with appropriate filters and `--json`
3. If the search returns results, summarize them clearly (date, sender, subject, snippet)
4. If the user wants to read a specific message, use `msgvault show-message <id> --json`
5. If the request is about aggregate patterns (e.g., "who emails me the most"), use the list-* commands
6. If the first query doesn't find what they want, try broader/narrower queries or different operators
7. When presenting results, always mention the message ID so the user can drill down

## Tips

- Combine operators: `from:alice@example.com after:2024-01-01 has:attachment`
- Use `--limit` to control result count (default 50)
- For vague requests, start with a broad text search, then narrow down
- If too many results, suggest adding date ranges or sender filters
- Use `--account` flag if the user has multiple accounts and wants to search a specific one
