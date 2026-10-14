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

## Skills

| Name                    | Purpose                                             |
| ----------------------- | --------------------------------------------------- |
| `agent-browser`         | Browser automation via `agent-browser` CLI          |
| `chezmoi`               | Safe chezmoi dotfile workflows and troubleshooting  |
| `fabric`                | Fabric.js geometry, rendering, serialization quirks |
| `grafana`               | Grafana dashboards and scenes app plugins           |
| `human-centered-design` | Human-centered design, usability, and UX heuristics |
| `layerchart`            | LayerChart visualizations for Svelte                |
| `msgvault`              | Search emails in msgvault archive                   |
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
