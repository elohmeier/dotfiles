# Pi Extensions

Use extensions for runtime behavior: tools, commands, shortcuts, custom UI, provider registration, compaction hooks, permission gates, session persistence, and resource discovery.

Source docs: `packages/coding-agent/docs/extensions.md`.
Source types: `packages/coding-agent/src/core/extensions/types.ts`.

## Extension Shape

An extension is a TypeScript module with a default factory:

```typescript
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export default function(pi: ExtensionAPI) {
  pi.registerTool({
    name: "greet",
    label: "Greet",
    description: "Greet someone by name",
    parameters: Type.Object({
      name: Type.String(),
    }),
    async execute(_toolCallId, params) {
      return {
        content: [{ type: "text", text: `Hello, ${params.name}` }],
        details: {},
      };
    },
  });

  pi.registerCommand("hello", {
    description: "Say hello",
    handler: async (args, ctx) => {
      ctx.ui.notify(`Hello ${args || "world"}`, "info");
    },
  });
}
```

The factory may be async. Pi waits for async factories before startup continues, so async provider/model discovery can register providers before model selection.

## Locations And Reload

Auto-discovered:

- `~/.pi/agent/extensions/*.ts`
- `~/.pi/agent/extensions/*/index.ts`
- `.pi/extensions/*.ts`
- `.pi/extensions/*/index.ts`

Use `pi -e ./my-extension.ts` for quick tests. Put extensions in auto-discovered locations for `/reload`.

Extensions run with full process permissions.

## Available Imports

Use:

- `@earendil-works/pi-coding-agent` for extension API/types and coding-agent UI components.
- `@earendil-works/pi-ai` for AI helpers and `StringEnum`.
- `@earendil-works/pi-agent-core` for lower-level agent types.
- `@earendil-works/pi-tui` for custom UI components.
- `typebox` for schemas.

Third-party runtime dependencies must be installed next to the extension or included in a pi package `dependencies`.

## Event Flow

Major event order:

1. `session_start`
2. `resources_discover`
3. `input`
4. prompt template / skill expansion
5. `before_agent_start`
6. `agent_start`
7. repeated turns:
   - `turn_start`
   - `context`
   - `before_provider_request`
   - `after_provider_response`
   - `message_start`, `message_update`, `message_end`
   - `tool_execution_start`
   - `tool_call`
   - `tool_execution_update`
   - `tool_result`
   - `tool_execution_end`
   - `turn_end`
8. `agent_end`

Session replacement emits `session_before_switch` or `session_before_fork`, then `session_shutdown`, then a new `session_start`.

Compaction emits `session_before_compact` and `session_compact`.

## Extension Context

`ExtensionContext` includes:

- `ui`: interaction and rendering APIs.
- `mode`: `"tui" | "rpc" | "json" | "print"`.
- `hasUI`: true in TUI/RPC dialog-capable modes.
- `cwd`.
- `sessionManager`: read-only session manager.
- `modelRegistry`.
- `model`.
- `isIdle()`, `signal`, `abort()`, `shutdown()`.
- `hasPendingMessages()`.
- `getContextUsage()`.
- `compact(options)`.
- `getSystemPrompt()`.

`ExtensionCommandContext` adds command-only session control:

- `waitForIdle()`
- `newSession()`
- `fork()`
- `navigateTree()`
- `switchSession()`
- `reload()`

Use command context for user-initiated session replacement. Event handlers should avoid replacing sessions directly unless they use exposed safe actions.

## UI API

`ctx.ui` supports:

- `select(title, options, opts?)`
- `confirm(title, message, opts?)`
- `input(title, placeholder?, opts?)`
- `notify(message, type?)`
- `setStatus(key, text)`
- `setWorkingMessage(message?)`
- `setWorkingVisible(visible)`
- `setWorkingIndicator(options?)`
- `setHiddenThinkingLabel(label?)`
- `setWidget(key, content, options?)`
- `setFooter(factory)`
- `setHeader(factory)`
- `setTitle(title)`
- `custom(factory, options?)`
- `pasteToEditor(text)`
- `setEditorText(text)`
- `getEditorText()`
- `editor(title, prefill?)`
- `addAutocompleteProvider(factory)`
- `setEditorComponent(factory)`
- theme access and tool expansion controls

Guard terminal-only custom components with `ctx.mode === "tui"`.

## Custom Tools

Tool definitions use TypeBox:

```typescript
import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const tool = defineTool({
  name: "status",
  label: "Status",
  description: "Return current status",
  parameters: Type.Object({
    verbose: Type.Optional(Type.Boolean()),
  }),
  async execute(_toolCallId, params, signal, onUpdate, ctx) {
    onUpdate?.({
      content: [{ type: "text", text: "Checking..." }],
      details: {},
    });
    if (signal?.aborted) throw new Error("Operation aborted");
    return {
      content: [{
        type: "text",
        text: params.verbose ? `cwd: ${ctx.cwd}` : "ok",
      }],
      details: {},
    };
  },
});
```

Tool definitions can include:

- `promptSnippet`
- `promptGuidelines`
- `prepareArguments`
- `executionMode`
- `renderShell`
- `renderCall`
- `renderResult`

Use `StringEnum` from `@earendil-works/pi-ai` instead of `Type.Enum` when Google compatibility matters.

## Tool Call And Result Hooks

Use `tool_call` to inspect or block execution. Return `{ block: true, reason }` to prevent a tool from running.

Use `tool_result` to modify `content`, `details`, or `isError` after execution.

Built-in tool event variants include `BashToolCallEvent`, `ReadToolCallEvent`, `EditToolCallEvent`, `WriteToolCallEvent`, `GrepToolCallEvent`, `FindToolCallEvent`, and `LsToolCallEvent`.

## Commands, Shortcuts, And Flags

Extensions can register:

- Slash commands with `pi.registerCommand(name, { description, handler })`.
- Shortcuts with `pi.registerShortcut(key, { description, handler })`.
- CLI flags with `pi.registerFlag(...)`.

Use configurable keybindings where possible. Do not hardcode behavior that should be user-remappable.

## Resource Discovery

`resources_discover` handlers can return:

```typescript
{
  skillPaths?: string[];
  promptPaths?: string[];
  themePaths?: string[];
}
```

Use this to provide generated or package-relative resources at startup/reload.

## Provider Registration

Use `pi.registerProvider(name, config)` for custom providers that fit existing APIs. Provider config can include:

- `baseUrl`
- `apiKey`
- `api`
- `headers`
- `compat`
- `models`
- `modelOverrides`

For fully custom APIs, register an API provider through `@earendil-works/pi-ai` or use extension-provided custom stream behavior where appropriate.

## Session Persistence

Use session custom entries for extension state:

- `appendEntry` / `sessionManager.appendCustomEntry`: persisted but not sent to LLM.
- custom messages: persisted and converted into LLM context.

Read the current branch through `ctx.sessionManager.getBranch()` and scan entries by `customType` on reload.

## Packaging Extensions

In pi packages, list Pi core packages as peer dependencies with `"*"` if imported:

- `@earendil-works/pi-ai`
- `@earendil-works/pi-agent-core`
- `@earendil-works/pi-coding-agent`
- `@earendil-works/pi-tui`
- `typebox`

Put non-Pi runtime dependencies in `dependencies`.

## Examples

Examples live under `packages/coding-agent/examples/extensions/`.

High-value examples:

- `tools.ts`: custom tools.
- `commands.ts`: slash commands.
- `permission-gate.ts`, `confirm-destructive.ts`, `protected-paths.ts`: tool gating.
- `custom-provider-anthropic/`, `custom-provider-gitlab-duo/`: providers.
- `custom-compaction.ts`: compaction hook.
- `qna.ts`, `question.ts`, `questionnaire.ts`: interactive UI.
- `modal-editor.ts`, `custom-footer.ts`, `custom-header.ts`, `widget-placement.ts`: UI surfaces.
- `subagent/`: sub-agent pattern.
- `plan-mode/`: plan-mode extension example.
