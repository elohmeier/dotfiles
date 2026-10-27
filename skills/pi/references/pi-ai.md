# Pi AI

Use `@earendil-works/pi-ai` when you need the provider/model layer without coding-agent sessions or built-in tools.

Source entry points:

- `packages/ai/src/index.ts`
- `packages/ai/src/types.ts`
- `packages/ai/src/stream.ts`
- `packages/ai/src/models.ts`
- `packages/ai/src/api-registry.ts`
- `packages/ai/src/images.ts`
- `packages/ai/src/image-models.ts`

## Main APIs

Text/chat:

- `getModel(provider, modelId)`
- `getProviders()`
- `getModels(provider)`
- `stream(model, context, options?)`
- `complete(model, context, options?)`
- `streamSimple(model, context, options?)`
- `completeSimple(model, context, options?)`

Images:

- `getImageModel(provider, modelId)`
- `getImageProviders()`
- `getImageModels(provider)`
- `generateImages(model, context, options?)`

Registry:

- `registerApiProvider(provider, sourceId?)`
- `getApiProvider(api)`
- `unregisterApiProviders(sourceId)`
- `clearApiProviders()`

Validation/helpers:

- `Type`, `Static`, `TSchema`
- `StringEnum(values, options?)`
- `validateToolCall(tools, toolCall)`
- `validateToolArguments(tool, toolCall)`
- `clampThinkingLevel(model, level)`
- `getSupportedThinkingLevels(model)`

## Context And Messages

`Context`:

```typescript
interface Context {
  systemPrompt?: string;
  messages: Message[];
  tools?: Tool[];
}
```

`Message` is:

- `UserMessage`
- `AssistantMessage`
- `ToolResultMessage`

Content blocks:

- Text: `{ type: "text", text }`
- Thinking: `{ type: "thinking", thinking }`
- Image: `{ type: "image", data, mimeType }`
- Tool call: `{ type: "toolCall", id, name, arguments }`

Tool results support text and image content.

## Streaming Events

`AssistantMessageEvent` variants:

- `start`
- `text_start`, `text_delta`, `text_end`
- `thinking_start`, `thinking_delta`, `thinking_end`
- `toolcall_start`, `toolcall_delta`, `toolcall_end`
- `done`
- `error`

Do not assume event groups are contiguous. Providers may interleave deltas for different content blocks. Use `contentIndex` to associate deltas with the right block.

`toolcall_delta` contains partial parsed arguments in `event.partial.content[event.contentIndex].arguments`. Treat partial arguments as incomplete.

## `stream` vs `streamSimple`

Use `stream` / `complete` for provider-specific options like OpenAI reasoning effort or Anthropic thinking budgets.

Use `streamSimple` / `completeSimple` for the unified option:

```typescript
await completeSimple(model, context, {
  reasoning: "medium",
});
```

`pi-agent-core` and `pi-coding-agent` use `streamSimple()` by default so thinking level is provider-neutral.

## Tool Definitions And Validation

Tools use TypeBox:

```typescript
import { StringEnum, type Tool, Type } from "@earendil-works/pi-ai";

const tool: Tool = {
  name: "calculate",
  description: "Calculate a simple operation",
  parameters: Type.Object({
    operation: StringEnum(["add", "subtract"] as const),
    left: Type.Number(),
    right: Type.Number(),
  }),
};
```

Use `StringEnum`, not `Type.Enum`, when schemas must work with Google and providers that reject `anyOf`/`const` enum shapes.

`validateToolArguments()` clones arguments, applies TypeBox conversion, performs additional JSON-schema primitive coercion for plain JSON schemas, and throws formatted errors on failure.

## Model Metadata

`Model` includes:

- `id`, `name`
- `api`, `provider`, `baseUrl`
- `reasoning`
- `thinkingLevelMap`
- `input`
- `cost`
- `contextWindow`, `maxTokens`
- `headers`
- `compat`

Built-in model metadata comes from generated files:

- `packages/ai/src/models.generated.ts`
- `packages/ai/src/image-models.generated.ts`

Do not directly edit generated metadata in pi-mono. Update generator scripts under `packages/ai/scripts/` and regenerate.

## Custom API Providers

Register APIs with:

```typescript
import { registerApiProvider } from "@earendil-works/pi-ai";

registerApiProvider({
  api: "my-api",
  stream(model, context, options) {
    return myStream(model, context, options);
  },
  streamSimple(model, context, options) {
    return myStreamSimple(model, context, options);
  },
});
```

Provider stream functions must return an `AssistantMessageEventStream`. Request/model/runtime failures should be encoded in the returned stream with `error` events and final assistant messages with `stopReason: "error" | "aborted"`.

## Custom Model Config

For the coding-agent CLI/SDK, custom models are usually configured via `~/.pi/agent/models.json` and loaded by `ModelRegistry`.

Custom providers can use supported APIs:

- `openai-completions`
- `openai-responses`
- `azure-openai-responses`
- `openai-codex-responses`
- `anthropic-messages`
- `google-generative-ai`
- `google-vertex`
- `mistral-conversations`
- `bedrock-converse-stream`

Compatibility settings exist for OpenAI-compatible, Responses-compatible, and Anthropic-compatible providers. Check `packages/ai/src/types.ts` and `packages/coding-agent/src/core/model-registry.ts` before guessing field names.

## Images API

Image generation is separate from chat/tool calling:

```typescript
import { generateImages, getImageModel } from "@earendil-works/pi-ai";

const model = getImageModel("openrouter", "google/gemini-2.5-flash-image");
const result = await generateImages(model, {
  input: [{ type: "text", text: "Generate a red circle." }],
});
```

Use `getImageModel()` and `generateImages()`, not `getModel()` or `stream()`.

## OAuth

OAuth utilities are exported from `@earendil-works/pi-ai/oauth` and from the root package as types. Coding-agent `AuthStorage` and `ModelRegistry` handle normal CLI/SDK OAuth use.

Provider examples include Anthropic, OpenAI Codex, GitHub Copilot, and Vertex-related flows under `packages/ai/src/utils/oauth/`.
