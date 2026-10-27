---
name: pi
description: Use when working with Pi, the @earendil-works/pi coding-agent ecosystem, pi CLI usage, pi-coding-agent SDK/RPC integration, extensions, skills, prompt templates, themes, pi packages, @earendil-works/pi-ai provider/model APIs, @earendil-works/pi-agent-core agent loops/tools/events, or @earendil-works/pi-tui terminal UI components. Use for explaining Pi internals, embedding Pi in other tools, extending the coding agent, or changing pi-mono code.
---

# Pi Usage

Use this skill to work with Pi as a CLI, as an embeddable coding-agent SDK, or as a set of lower-level TypeScript libraries.

## First Checks

- If you are inside the `pi` repository, read `AGENTS.md` before editing and follow its command rules.
- Prefer current source and package docs over memory. Pi changes quickly, especially model/provider metadata and extension APIs.
- Use `rg` for symbols and exact event names. Do not infer event contracts from README snippets when source types are nearby.
- Check `packages/*/README.md`, then the relevant `packages/*/src` files, then focused tests.
- Do not hand-edit generated model metadata. In pi-mono, update generator scripts under `packages/ai/scripts/` and regenerate.

## Reference Map

Load only the references needed for the task:

- `references/architecture.md`: package boundaries, dependency direction, runtime flow, source map, development rules.
- `references/cli-and-resources.md`: CLI modes, config paths, sessions, context files, skills, prompts, themes, packages.
- `references/coding-agent-sdk.md`: `@earendil-works/pi-coding-agent` SDK, `AgentSession`, runtimes, built-in tool factories.
- `references/extensions.md`: extension factory, event flow, command/tool/UI APIs, custom providers, packaging.
- `references/pi-ai.md`: `@earendil-works/pi-ai` models, providers, stream events, tools, images, OAuth/custom provider hooks.
- `references/agent-core.md`: `@earendil-works/pi-agent-core` `Agent`, low-level loops, events, queues, tool hooks.
- `references/tui.md`: `@earendil-works/pi-tui` components, rendering constraints, overlays, keyboard handling.
- `references/source-navigation.md`: high-value source files, docs, examples, and test locations.

## Common Decision Points

- Use `pi` CLI for terminal coding workflows and quick automation.
- Use `@earendil-works/pi-coding-agent` when embedding the full coding agent, sessions, built-in tools, extensions, resources, or RPC.
- Use `@earendil-works/pi-agent-core` when building a custom agent loop with your own UI/session layer.
- Use `@earendil-works/pi-ai` when you only need a unified multi-provider LLM API.
- Use `@earendil-works/pi-tui` when building terminal UI components or custom extension UI.
- Use extensions for runtime behavior: tools, commands, hooks, custom UI, providers, compaction, permission gates.
- Use skills for model-facing procedural knowledge and bundled references/scripts.
- Use prompt templates for reusable prompt text, not runtime behavior.
- Use pi packages to distribute extensions, skills, prompts, and themes through npm, git, or local paths.

## Implementation Rules

- For TypeScript checked by pi-mono root config, use erasable TypeScript syntax only.
- Use top-level imports only. Do not use dynamic imports or inline type imports.
- Define tools with TypeBox schemas; prefer `StringEnum` from `@earendil-works/pi-ai` for string enums that must work across providers.
- For custom Pi extensions, import extension types from `@earendil-works/pi-coding-agent` and schemas from `typebox`.
- For custom TUI components, every `render(width)` line must fit within `width`; use `truncateToWidth`, wrapping, or stable dimensions.
- For code changes in pi-mono, run `npm run check` after non-doc edits. Run focused tests only when creating or changing tests.
