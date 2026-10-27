# Agent Core

Use `@earendil-works/pi-agent-core` when building a custom agent runtime with Pi's LLM loop, tool execution, queues, and event stream, but without the full coding-agent CLI/session/resource stack.

Source entry points:

- `packages/agent/src/index.ts`
- `packages/agent/src/agent.ts`
- `packages/agent/src/agent-loop.ts`
- `packages/agent/src/types.ts`
- `packages/agent/src/proxy.ts`

## Primary Exports

- `Agent`
- `agentLoop()`
- `agentLoopContinue()`
- `streamProxy()`
- `AgentMessage`, `AgentState`, `AgentContext`
- `AgentTool`, `AgentToolResult`, `AgentEvent`
- compaction/session/skill/prompt harness utilities
- `NodeExecutionEnv` from `@earendil-works/pi-agent-core/node`

## `Agent`

Minimal usage:

```typescript
import { Agent } from "@earendil-works/pi-agent-core";
import { getModel } from "@earendil-works/pi-ai";

const agent = new Agent({
  initialState: {
    systemPrompt: "You are helpful.",
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

agent.subscribe((event) => {
  if (
    event.type === "message_update"
    && event.assistantMessageEvent.type === "text_delta"
  ) {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await agent.prompt("Hello");
```

Important options:

- `initialState`
- `convertToLlm`
- `transformContext`
- `streamFn`
- `getApiKey`
- `onPayload`, `onResponse`
- `beforeToolCall`, `afterToolCall`
- `prepareNextTurn`
- `steeringMode`, `followUpMode`
- `sessionId`
- `thinkingBudgets`
- `transport`
- `maxRetryDelayMs`
- `toolExecution`

## State

`AgentState` contains:

- `systemPrompt`
- `model`
- `thinkingLevel`
- `tools`
- `messages`
- `isStreaming`
- `streamingMessage`
- `pendingToolCalls`
- `errorMessage`

Assigning `state.tools` or `state.messages` copies the top-level array. Mutating the returned array mutates current state.

## Events

`AgentEvent` variants:

- `agent_start`
- `agent_end`
- `turn_start`
- `turn_end`
- `message_start`
- `message_update`
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`

`Agent.subscribe()` listeners are awaited in registration order. `agent_end` is the last event, but the run is not idle until awaited `agent_end` listeners settle.

## Prompting And Queues

Methods:

- `prompt(text, images?)`
- `prompt(AgentMessage | AgentMessage[])`
- `continue()`
- `steer(message)`
- `followUp(message)`
- `clearSteeringQueue()`
- `clearFollowUpQueue()`
- `clearAllQueues()`
- `abort()`
- `waitForIdle()`
- `reset()`

Steering messages are injected after the current assistant turn and tool batch. Follow-up messages are injected only after the agent would otherwise stop.

Queue modes:

- `"one-at-a-time"`
- `"all"`

## Low-Level Loops

Use `agentLoop()` and `agentLoopContinue()` for direct event-stream control:

```typescript
import { agentLoop } from "@earendil-works/pi-agent-core";

for await (const event of agentLoop([userMessage], context, config)) {
  console.log(event.type);
}
```

Low-level loop streams are observational. They preserve event order, but they do not wait for your async event handling to settle before later producer phases continue. Use `Agent` when message processing must be a barrier before tool preflight.

## Tools

`AgentTool` extends `pi-ai` `Tool` with:

- `label`
- `prepareArguments?`
- `execute(toolCallId, params, signal, onUpdate?)`
- `executionMode?`

Tool result:

```typescript
{
  content: [{ type: "text", text: "..." }],
  details: {},
  terminate?: true
}
```

Throw errors from tools. The agent catches them and reports error tool results to the model.

`executionMode`:

- `"parallel"`: default; preflight sequentially, execute allowed tools concurrently, emit end events as tools finish, persist tool results in assistant source order.
- `"sequential"`: execute tool calls one by one.

If any tool in a batch requires sequential execution, the whole batch runs sequentially.

## Tool Hooks

`beforeToolCall` receives:

- `assistantMessage`
- `toolCall`
- validated `args`
- current `context`

Return `{ block: true, reason }` to block execution.

`afterToolCall` receives:

- `assistantMessage`
- `toolCall`
- validated `args`
- `result`
- `isError`
- current `context`

Return overrides for `content`, `details`, `isError`, or `terminate`. There is no deep merge.

## Early Termination

A tool result can set `terminate: true`. The loop stops after a tool batch only when every finalized tool result in that batch has `terminate: true`.

## Context Conversion

`AgentMessage` is extensible via declaration merging. LLMs only accept `Message` from `pi-ai`.

Use `convertToLlm` to filter or convert custom messages:

```typescript
const agent = new Agent({
  convertToLlm: (messages) =>
    messages.flatMap((message) => {
      if (message.role === "notification") return [];
      return [message];
    }),
});
```

Use `transformContext` for pruning, compaction, or injecting external context before conversion.

## Proxy Streaming

`streamProxy()` lets browser/client apps proxy LLM calls through a backend. It posts to `${proxyUrl}/api/stream`, expects server-sent proxy events, reconstructs the partial assistant message client-side, and returns an `AssistantMessageEventStream`.

Use it as an `Agent` `streamFn`.
