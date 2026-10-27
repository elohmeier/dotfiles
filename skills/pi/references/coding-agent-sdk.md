# Coding Agent SDK

Use `@earendil-works/pi-coding-agent` when you want the full coding-agent runtime: sessions, settings, model registry, auth, built-in tools, extensions, skills, prompt templates, themes, compaction, and run modes.

## Primary Exports

Source: `packages/coding-agent/src/index.ts`.

Important exports:

- `createAgentSession`, `createAgentSessionFromServices`, `createAgentSessionServices`
- `createAgentSessionRuntime`, `AgentSessionRuntime`
- `AgentSession`, `AgentSessionEvent`, `PromptOptions`
- `AuthStorage`, `ModelRegistry`, `SettingsManager`, `SessionManager`
- Built-in tool factories: `createReadTool`, `createBashTool`, `createEditTool`, `createWriteTool`, `createGrepTool`, `createFindTool`, `createLsTool`, `createCodingTools`, `createReadOnlyTools`
- Extension types: `ExtensionAPI`, `ExtensionContext`, `ExtensionCommandContext`, `ToolDefinition`, event types
- Resource helpers: `DefaultResourceLoader`, `loadSkills`, `loadPromptTemplates`
- Run modes: `InteractiveMode`, `runPrintMode`, `runRpcMode`, `RpcClient`

## Minimal SDK Session

```typescript
import {
  AuthStorage,
  createAgentSession,
  ModelRegistry,
  SessionManager,
} from "@earendil-works/pi-coding-agent";

const authStorage = AuthStorage.create();
const modelRegistry = ModelRegistry.create(authStorage);

const { session } = await createAgentSession({
  sessionManager: SessionManager.inMemory(),
  authStorage,
  modelRegistry,
});

session.subscribe((event) => {
  if (
    event.type === "message_update"
    && event.assistantMessageEvent.type === "text_delta"
  ) {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await session.prompt("What files are in the current directory?");
```

## `createAgentSession()`

Source: `packages/coding-agent/src/core/sdk.ts`.

Key options:

- `cwd`, `agentDir`
- `authStorage`, `modelRegistry`
- `model`, `thinkingLevel`, `scopedModels`
- `tools`, `excludeTools`, `noTools`
- `customTools`
- `resourceLoader`
- `sessionManager`, `settingsManager`

Behavior:

- Uses `DefaultResourceLoader` unless one is provided.
- Restores model/thinking from an existing session when possible.
- Chooses an initial model from settings/provider defaults when no model is passed.
- Creates an `Agent` with a `streamFn` that resolves model auth and provider attribution headers.
- Wires extension hooks into context, provider request/response, tool call, and tool result phases.
- Defaults active built-in tools to `read`, `bash`, `edit`, `write`.

## `AgentSession`

Source: `packages/coding-agent/src/core/agent-session.ts`.

`AgentSession` wraps the core `Agent` with:

- prompt handling, images, prompt template expansion, and queueing
- session persistence
- extension event emission
- active tool registry
- compaction and branch summarization
- auto-retry
- model and thinking-level controls
- bash execution for `!` and `!!`
- tree navigation and HTML export

Useful methods and properties:

- `prompt(text, options?)`
- `steer(text)`, `followUp(text)`
- `subscribe(listener)`
- `setModel(model)`, `setThinkingLevel(level)`, `cycleModel()`, `cycleThinkingLevel()`
- `compact(customInstructions?)`, `abortCompaction()`
- `navigateTree(targetId, options?)`
- `abort()`, `dispose()`
- `agent`, `state`, `messages`, `isStreaming`
- `sessionFile`, `sessionId`

During streaming, `prompt()` needs `streamingBehavior: "steer" | "followUp"` or use `steer()` / `followUp()` directly.

## Session Runtime

Use `createAgentSessionRuntime()` when your integration needs to replace the active session, not just prompt an existing one.

Session replacement operations:

- `newSession()`
- `switchSession()`
- `fork()`
- clone flows through `fork(entryId, { position: "at" })`
- `importFromJsonl()`

Important behavior:

- `runtime.session` changes after replacement.
- Re-subscribe after replacement.
- Re-bind extensions after replacement if you manage extension bindings.
- Replacement failures throw; callers own UI/error handling.

## Built-In Tool Factories

Built-in tools are available as both `ToolDefinition` and `AgentTool` factories.

Use `ToolDefinition` when working inside coding-agent extension/session machinery. Use `AgentTool` when working with `pi-agent-core` directly.

Default coding tools:

- `read`: reads text and supported images; truncates large text; supports `offset`/`limit`.
- `bash`: executes shell command, streams output, truncates and stores full output when needed.
- `edit`: exact replacement edits, supports multiple non-overlapping edits in one call.
- `write`: creates or overwrites files and parent directories.

Read-only tools:

- `grep`
- `find`
- `ls`

Custom operation hooks allow remote/sandboxed implementations:

- `ReadOperations`
- `BashOperations`
- `EditOperations`
- `WriteOperations`
- `GrepOperations`
- `FindOperations`
- `LsOperations`

## Custom Tools In SDK

Use TypeBox schemas and `defineTool` if inference would otherwise widen params:

```typescript
import {
  createAgentSession,
  defineTool,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const pingTool = defineTool({
  name: "ping",
  label: "Ping",
  description: "Return a fixed ping response",
  parameters: Type.Object({
    label: Type.String(),
  }),
  async execute(_toolCallId, params) {
    return {
      content: [{ type: "text", text: `pong: ${params.label}` }],
      details: {},
    };
  },
});

const { session } = await createAgentSession({
  customTools: [pingTool],
});
```

Tool execution receives `ctx: ExtensionContext` in the coding-agent `ToolDefinition` form.

## Auth And Models

`AuthStorage` manages API keys and OAuth credentials. File storage uses locking and mode `0600`; in-memory storage is available for tests/integrations.

`ModelRegistry` loads:

- built-in generated model metadata from `pi-ai`
- custom `models.json`
- provider registrations from extensions
- OAuth provider modifications

`models.json` supports provider configs, custom models, built-in overrides, headers, compat settings, and API key references.

## RPC Integration

For non-Node integrations, run:

```bash
pi --mode rpc
```

Use strict LF-delimited JSONL framing. Commands go to stdin; responses and agent events come from stdout. Source: `packages/coding-agent/src/modes/rpc/rpc-types.ts`.

The SDK also exports `RpcClient`, which spawns a `pi --mode rpc` process and offers typed methods.

## Examples

Working examples live under `packages/coding-agent/examples/sdk/`:

- `01-minimal.ts`
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
