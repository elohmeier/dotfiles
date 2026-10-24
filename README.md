# skills

Personal agent skills for use with the [skills CLI](https://github.com/vercel-labs/skills).

## Install

```bash
npx skills add elohmeier/skills -g
```

Or pick specific skills/agents:

```bash
npx skills add elohmeier/skills -s typst -a claude-code -g
```

To install from this local checkout, run the helper from the project that
should receive the skills:

```bash
path/to/skills/scripts/install-local-skills.sh
```

It opens the interactive skill and agent menus. The calling directory remains
the project installation target. Pass `-g` for a global installation or any
other `skills add` option after the script name, for example:

```bash
path/to/skills/scripts/install-local-skills.sh \
  --skill n64 agent-publish --agent claude-code codex --yes
```

## Skills

| Name                    | Purpose                                             |
| ----------------------- | --------------------------------------------------- |
| `agent-browser`         | Browser automation via `agent-browser` CLI          |
| `agent-publish`         | Publish project artifacts through shared Caddy      |
| `chezmoi`               | Safe chezmoi dotfile workflows and troubleshooting  |
| `fabric`                | Fabric.js geometry, rendering, serialization quirks |
| `grafana`               | Grafana dashboards and scenes app plugins           |
| `human-centered-design` | Human-centered design, usability, and UX heuristics |
| `layerchart`            | LayerChart visualizations for Svelte                |
| `msgvault`              | Search emails in msgvault archive                   |
| `n64`                   | Build, debug, and validate N64 homebrew             |
| `opendataloader-pdf`    | PDF text/table extraction CLI                       |
| `secret-entry`          | Request secrets into SOPS env files or pass         |
| `taskjuggler`           | Text-based project scheduling and reporting         |
| `typst`                 | Typst document authoring and scripting              |
| `vnc-browser`           | Share a headed agent-browser session over noVNC     |

## Maintenance

Vendor the `agent-browser` skill from a local upstream checkout:

```bash
scripts/vendor-agent-browser-skill.sh
```

By default this reads
`/var/home/gordon/repos/github.com/vercel-labs/agent-browser/skill-data/core`.
Pass a checkout path or set `AGENT_BROWSER_REPO` to use another location. The
script updates that checkout with `git fetch --prune` and a fast-forward-only
merge before copying.
