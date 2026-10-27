# Agent skills

Personal agent skills maintained alongside the tools and configuration they use.
The source tree was imported from the former skills repository at commit
`b77b1f8767a8f9861fb5b9e952e025df5c82757c`. Its complete Git history is preserved
on the `skills-history` branch of this repository.

## Install

Install or update all skills for Claude Code and Codex from this checkout:

```sh
djust install-skills
```

Installed skills are copies. Edit the sources here and rerun the command after
changes or `chezmoi update`. Skill folders include their references, assets,
templates, and executable scripts.

To install from GitHub:

```sh
npx skills add elohmeier/dotfiles --skill '*' --agent claude-code --agent codex --global --yes
```

To select skills and agents interactively for another project, run the helper
from that project's directory:

```sh
path/to/dotfiles/scripts/install-local-skills.sh
path/to/dotfiles/scripts/install-local-skills.sh --skill n64 agent-publish --agent claude-code codex --yes
```

The calling directory remains the project installation target. Pass `--global`
to install globally instead. Existing skills from other sources are retained.

Sandbox agents have separate homes. Install skills there or mount their
directories as described in the [sandbox documentation](../home/dot_config/pi-less-yolo/README.md#configuration-and-authentication).

## Skills

| Name                        | Purpose                                              |
| --------------------------- | ---------------------------------------------------- |
| `agent-browser`             | Browser automation via the agent-browser CLI         |
| `agent-publish`             | Publish project artifacts through shared Caddy       |
| `apply-telemetry-semantics` | Apply OTel Semantic Conventions and ECS semantics    |
| `chezmoi`                   | Manage and troubleshoot chezmoi dotfiles             |
| `fabric`                    | Fabric.js geometry, rendering, and serialization     |
| `grafana`                   | Grafana dashboards and scenes app plugins            |
| `human-centered-design`     | Human-centered design and usability reviews          |
| `kanboard`                  | Inspect and change Kanboard boards and tasks         |
| `layerchart`                | LayerChart visualizations for Svelte                 |
| `msgvault`                  | Search emails in the msgvault archive                |
| `n64`                       | Build, debug, and validate N64 homebrew              |
| `opendataloader-pdf`        | Extract text and tables from PDFs                    |
| `pi`                        | Pi coding-agent configuration and development        |
| `secret-entry`              | Request secrets into SOPS, pass, or host credentials |
| `taskjuggler`               | Text-based project scheduling and reporting          |
| `typst`                     | Typst document authoring and scripting               |
| `vnc-browser`               | Share a headed agent-browser session over noVNC      |

## Maintenance

Vendor the agent-browser skill from a local upstream checkout:

```sh
scripts/vendor-agent-browser-skill.sh /path/to/vercel-labs/agent-browser
```

The helper fetches and fast-forwards that checkout, copies `skill-data/core` to
`skills/agent-browser`, and sets the skill name to `agent-browser`.

Formatting uses the root dprint configuration, with TypeScript support scoped
to this directory. Run `dprint fmt skills` after editing skills.
