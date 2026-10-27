# Pi Architecture

## Package Boundaries

Pi is a TypeScript monorepo with four primary packages:

| Package                           | Use for                                                                                                   | Depends on                         |
| --------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `@earendil-works/pi-ai`           | Unified model/provider API, streaming, tool schemas, model registries, image generation, OAuth utilities  | Provider SDKs and TypeBox          |
| `@earendil-works/pi-agent-core`   | Stateful agent loop, tool execution, queues, event stream, context transforms, session harness primitives | `pi-ai`                            |
| `@earendil-works/pi-tui`          | Terminal UI components, differential rendering, overlays, inputs, keyboard parsing, inline images         | Terminal utilities                 |
| `@earendil-works/pi-coding-agent` | `pi` CLI, SDK, sessions, built-in coding tools, extensions, skills, prompts, themes, packages, RPC        | `pi-ai`, `pi-agent-core`, `pi-tui` |

The dependency direction is one-way: `coding-agent` composes the other three packages. Avoid putting coding-agent behavior into `pi-ai`, `agent-core`, or `tui` unless the lower package genuinely owns that concept.

## Runtime Flow

High-level CLI/SDK flow:

1. CLI parses args in `packages/coding-agent/src/cli/args.ts`.
2. `main()` builds services, auth/model registry, settings, resource loader, and session manager.
3. `DefaultResourceLoader` discovers extensions, skills, prompt templates, themes, context files, and system prompt files.
4. `createAgentSession()` creates an `Agent` from `pi-agent-core`, wires `convertToLlm`, model auth, provider hooks, context hooks, and tool hooks.
5. `AgentSession` wraps the core agent with session persistence, compaction, retry, model/thinking controls, extension event emission, slash commands, and built-in tools.
6. A run mode (`interactive`, `print`, `json`, or `rpc`) binds I/O around `AgentSession`.
7. The core `Agent` calls `streamSimple()` from `pi-ai`, emits message and tool events, executes tools, drains steering/follow-up queues, and ends the run.

## Message and Tool Flow

`pi-agent-core` owns the LLM loop:

`AgentMessage[] -> transformContext() -> AgentMessage[] -> convertToLlm() -> Message[] -> streamSimple() -> AssistantMessage -> tool execution -> ToolResultMessage[]`

Important distinctions:

- `AgentMessage` can include app-specific custom messages.
- `Message` from `pi-ai` is the LLM-compatible union: `user`, `assistant`, `toolResult`.
- `convertToLlm` is the boundary where custom/session/UI-only messages are filtered or converted.
- Tool arguments are validated against TypeBox schemas before execution.
- Tools should throw on failure; the runtime converts failures to error tool results.

## Coding Agent Resource Model

The coding agent loads resources from these categories:

- Context files: `AGENTS.md` or `CLAUDE.md`.
- System prompt files: `SYSTEM.md` and `APPEND_SYSTEM.md`.
- Skills: model-facing instructions and resources.
- Prompt templates: markdown prompts exposed as slash commands.
- Extensions: TypeScript runtime modules.
- Themes: interactive-mode theme JSON.
- Pi packages: bundles of extensions, skills, prompts, and themes.

`DefaultResourceLoader` handles the layered discovery and allows extensions to add resources at `resources_discover`.

## Source Map

Core source entry points:

- Root packages: `package.json`, `packages/*/package.json`, `packages/*/README.md`.
- AI API: `packages/ai/src/index.ts`, `types.ts`, `stream.ts`, `models.ts`, `api-registry.ts`.
- Agent core: `packages/agent/src/index.ts`, `agent.ts`, `agent-loop.ts`, `types.ts`, `proxy.ts`.
- Coding agent SDK: `packages/coding-agent/src/index.ts`, `core/sdk.ts`, `core/agent-session.ts`, `core/agent-session-runtime.ts`.
- Extension API: `packages/coding-agent/src/core/extensions/types.ts`, `loader.ts`, `runner.ts`, `wrapper.ts`.
- Resources: `packages/coding-agent/src/core/resource-loader.ts`, `skills.ts`, `prompt-templates.ts`, `package-manager.ts`.
- Sessions: `packages/coding-agent/src/core/session-manager.ts`.
- Built-in tools: `packages/coding-agent/src/core/tools/*.ts`.
- TUI: `packages/tui/src/index.ts`, `tui.ts`, `terminal.ts`, `keys.ts`, `components/*`.

## Development Rules

When modifying pi-mono:

- Read relevant files in full before broad edits.
- Follow existing package boundaries and local helpers.
- Keep TypeScript erasable under root-checked source and tests.
- Use `npm install --ignore-scripts` for dependency hydration and `npm install --package-lock-only --ignore-scripts` for lock refreshes.
- After code changes, run `npm run check`.
- Run `./test.sh` for non-e2e tests unless a focused package test is more appropriate.
- For coding-agent suite regressions, use `packages/coding-agent/test/suite/harness.ts` and faux providers.
- Never directly edit `packages/ai/src/models.generated.ts`; update generator scripts and regenerate.
