# Source Navigation

Use this map to find the right source quickly.

## Package Docs

- Root overview: `README.md`
- AI package: `packages/ai/README.md`
- Agent core: `packages/agent/README.md`
- Coding agent: `packages/coding-agent/README.md`
- TUI: `packages/tui/README.md`

## Coding Agent Docs

High-value docs under `packages/coding-agent/docs/`:

- `quickstart.md`: install and first use.
- `usage.md`: CLI usage and mode details.
- `providers.md`: provider setup.
- `models.md`: custom models and model matching.
- `custom-provider.md`: custom provider configuration.
- `settings.md`: settings schema and behavior.
- `sessions.md`: session commands.
- `session-format.md`: JSONL session schema and tree model.
- `compaction.md`: context compaction.
- `skills.md`: Pi skill discovery and validation.
- `prompt-templates.md`: prompt template format and substitution.
- `extensions.md`: extension API and events.
- `packages.md`: pi package installation and manifests.
- `rpc.md`: JSONL RPC protocol.
- `json.md`: JSON run mode.
- `sdk.md`: programmatic usage.
- `tui.md`: interactive TUI details.
- `themes.md`: theme files.
- `containerization.md`: sandbox/container patterns.

## AI Package Source

- `src/index.ts`: public exports.
- `src/types.ts`: message/content/model/tool/event types and provider compat settings.
- `src/stream.ts`: `stream`, `complete`, `streamSimple`, `completeSimple`.
- `src/models.ts`: built-in model registry helpers and thinking-level clamping.
- `src/models.generated.ts`: generated text model metadata. Do not hand-edit.
- `src/image-models.ts`: image model registry.
- `src/image-models.generated.ts`: generated image model metadata. Do not hand-edit.
- `src/images.ts`: `generateImages`.
- `src/api-registry.ts`: custom API provider registry.
- `src/images-api-registry.ts`: image API provider registry.
- `src/providers/register-builtins.ts`: built-in text provider registration.
- `src/providers/images/register-builtins.ts`: built-in image provider registration.
- `src/utils/validation.ts`: TypeBox argument validation and coercion.
- `src/utils/typebox-helpers.ts`: `StringEnum`.
- `src/utils/oauth/`: OAuth utilities and providers.
- `scripts/generate-models.ts`: text model generator.
- `scripts/generate-image-models.ts`: image model generator.

## Agent Core Source

- `src/index.ts`: public exports.
- `src/node.ts`: Node-specific export.
- `src/types.ts`: agent state, config, tools, events.
- `src/agent.ts`: stateful `Agent`.
- `src/agent-loop.ts`: low-level run loop and tool execution.
- `src/proxy.ts`: proxy stream function.
- `src/harness/compaction/`: compaction utilities.
- `src/harness/session/`: session repositories and storage.
- `src/harness/skills.ts`: generic skill helpers.
- `src/harness/prompt-templates.ts`: generic prompt template helpers.

## Coding Agent Source

CLI and run modes:

- `src/cli.ts`, `src/main.ts`
- `src/cli/args.ts`
- `src/modes/interactive/interactive-mode.ts`
- `src/modes/print-mode.ts`
- `src/modes/rpc/rpc-mode.ts`
- `src/modes/rpc/rpc-types.ts`
- `src/modes/rpc/rpc-client.ts`
- `src/modes/rpc/jsonl.ts`

SDK and runtime:

- `src/index.ts`
- `src/core/sdk.ts`
- `src/core/agent-session.ts`
- `src/core/agent-session-runtime.ts`
- `src/core/agent-session-services.ts`

Auth/models/settings:

- `src/core/auth-storage.ts`
- `src/core/model-registry.ts`
- `src/core/model-resolver.ts`
- `src/core/settings-manager.ts`
- `src/core/resolve-config-value.ts`

Resources:

- `src/core/resource-loader.ts`
- `src/core/package-manager.ts`
- `src/core/skills.ts`
- `src/core/prompt-templates.ts`
- `src/core/system-prompt.ts`
- `src/core/source-info.ts`

Extensions:

- `src/core/extensions/types.ts`
- `src/core/extensions/index.ts`
- `src/core/extensions/loader.ts`
- `src/core/extensions/runner.ts`
- `src/core/extensions/wrapper.ts`

Tools:

- `src/core/tools/index.ts`
- `src/core/tools/read.ts`
- `src/core/tools/bash.ts`
- `src/core/tools/edit.ts`
- `src/core/tools/write.ts`
- `src/core/tools/grep.ts`
- `src/core/tools/find.ts`
- `src/core/tools/ls.ts`
- `src/core/tools/file-mutation-queue.ts`
- `src/core/tools/tool-definition-wrapper.ts`

Sessions and compaction:

- `src/core/session-manager.ts`
- `src/core/compaction/index.ts`
- `src/core/compaction/compaction.ts`
- `src/core/compaction/branch-summarization.ts`

Interactive UI:

- `src/modes/interactive/components/`
- `src/modes/interactive/theme/theme.ts`
- `src/core/export-html/`

## TUI Source

- `src/index.ts`: public exports.
- `src/tui.ts`: `TUI`, `Container`, overlays, focus, rendering.
- `src/terminal.ts`: `Terminal`, `ProcessTerminal`, keyboard protocol negotiation.
- `src/keys.ts`: key parser and `Key` helper.
- `src/keybindings.ts`: keybinding manager.
- `src/stdin-buffer.ts`: input sequence and paste buffering.
- `src/utils.ts`: width, truncation, ANSI wrapping.
- `src/terminal-image.ts`: Kitty/iTerm image rendering.
- `src/components/`: built-in components.

## Examples

SDK:

- `packages/coding-agent/examples/sdk/01-minimal.ts`
- `02-custom-model.ts`
- `03-custom-prompt.ts`
- `04-skills.ts`
- `05-tools.ts`
- `06-extensions.ts`
- `07-context-files.ts`
- `08-prompt-templates.ts`
- `09-api-keys-and-oauth.ts`
- `10-settings.ts`
- `11-sessions.ts`
- `12-full-control.ts`
- `13-session-runtime.ts`

Extensions:

- `packages/coding-agent/examples/extensions/tools.ts`
- `commands.ts`
- `permission-gate.ts`
- `protected-paths.ts`
- `custom-compaction.ts`
- `custom-provider-anthropic/`
- `custom-provider-gitlab-duo/`
- `dynamic-resources/`
- `plan-mode/`
- `subagent/`
- `qna.ts`
- `modal-editor.ts`
- `custom-footer.ts`
- `custom-header.ts`

## Tests

Package tests:

- `packages/ai/test/`
- `packages/agent/test/`
- `packages/coding-agent/test/`
- `packages/tui/test/`

Coding-agent suite:

- `packages/coding-agent/test/suite/harness.ts`
- `packages/coding-agent/test/suite/regressions/`

Use faux providers for coding-agent suite tests. Do not use real provider APIs for regression tests.

Command guidance in pi-mono:

- Run `npm run check` after code changes.
- Use `./test.sh` for non-e2e suite runs unless a focused package test is required.
- Run focused Vitest from package root with `node ../../node_modules/vitest/dist/cli.js --run test/specific.test.ts`.
