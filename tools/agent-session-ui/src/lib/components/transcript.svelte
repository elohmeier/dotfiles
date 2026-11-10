<script lang="ts">
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert';
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check';
	import ImageIcon from '@lucide/svelte/icons/image';
	import ScrollTextIcon from '@lucide/svelte/icons/scroll-text';
	import WrenchIcon from '@lucide/svelte/icons/wrench';
	import { onMount } from 'svelte';
	import * as Bubble from '#lib/components/ui/bubble/index.js';
	import * as CodeBlock from '#lib/components/ui/code-block/index.js';
	import * as Marker from '#lib/components/ui/marker/index.js';
	import * as Message from '#lib/components/ui/message/index.js';
	import * as MessageScroller from '#lib/components/ui/message-scroller/index.js';
	import * as Trace from '#lib/components/ui/trace/index.js';
	import type { Block, Item } from '#lib/api.js';

	let { messages, focus }: { messages: Item[]; focus: string | null } = $props();

	type Tool = Extract<Block, { type: 'tool' }>;
	type Segment = { tools: Tool[] } | { block: Exclude<Block, Tool> };

	function segments(blocks: Block[]) {
		const result: Segment[] = [];
		for (const block of blocks) {
			const last = result.at(-1);
			if (block.type !== 'tool') result.push({ block });
			else if (last && 'tools' in last) last.tools.push(block);
			else result.push({ tools: [block] });
		}
		return result;
	}

	function summary(tool: Tool) {
		try {
			const input = JSON.parse(tool.input);
			const value = ['command', 'cmd', 'file_path', 'path', 'pattern', 'query', 'url', 'description']
				.map((key) => input?.[key])
				.find((value) => value);
			return String(Array.isArray(value) ? value.join(' ') : (value ?? '')).split('\n')[0];
		} catch {
			return tool.input.split('\n')[0];
		}
	}

	function counts(tools: Tool[]) {
		const names = new Map<string, number>();
		for (const tool of tools) names.set(tool.name, (names.get(tool.name) ?? 0) + 1);
		return [...names].map(([name, count]) => (count > 1 ? `${name} ×${count}` : name)).join(' · ');
	}

	const time = (timestamp: string) =>
		timestamp ? new Date(timestamp).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '';

	const scroller = MessageScroller.useMessageScroller();
	onMount(() => {
		if (focus) scroller.scrollToMessage(focus);
	});
</script>

{#snippet tool(tool: Tool)}
	<Trace.Collapsible>
		<Trace.CollapsibleTrigger>
			<Trace.Line status={tool.error ? 'error' : undefined}>
				<Trace.Icon>
					{#if tool.error}<CircleAlertIcon />{:else}<CircleCheckIcon />{/if}
				</Trace.Icon>
				<Trace.Title class="truncate">
					<span class="font-medium">{tool.name}</span>
					<span class="font-mono text-xs">{summary(tool)}</span>
				</Trace.Title>
			</Trace.Line>
		</Trace.CollapsibleTrigger>
		<Trace.CollapsibleContent class="flex flex-col gap-2">
			{#if tool.input}
				<CodeBlock.Root size="sm">
					<CodeBlock.Content wrap class="max-h-64" code={tool.input} />
				</CodeBlock.Root>
			{/if}
			{#if tool.output}
				<CodeBlock.Root size="sm" variant={tool.error ? 'destructive' : 'default'}>
					<CodeBlock.Content wrap class="max-h-64" code={tool.output} />
				</CodeBlock.Root>
			{/if}
		</Trace.CollapsibleContent>
	</Trace.Collapsible>
{/snippet}

<MessageScroller.Root class="flex-1">
	<MessageScroller.Viewport>
		<MessageScroller.Content class="mx-auto w-full max-w-3xl gap-6 px-6 py-8">
			{#each messages as item (item.id)}
				<MessageScroller.Item messageId={item.id} scrollAnchor={item.role === 'user'}>
					{#if item.role === 'user'}
						<Message.Root align="end">
							<Message.Content>
								{#each item.blocks as block, index (index)}
									{#if block.type === 'summary'}
										<Trace.Collapsible>
											<Trace.CollapsibleTrigger>
												<Trace.Line>
													<Trace.Icon><ScrollTextIcon /></Trace.Icon>
													<Trace.Title>Context summary</Trace.Title>
												</Trace.Line>
											</Trace.CollapsibleTrigger>
											<Trace.CollapsibleContent class="text-sm whitespace-pre-wrap">
												{block.text}
											</Trace.CollapsibleContent>
										</Trace.Collapsible>
									{:else if block.type === 'text'}
										<Bubble.Root>
											<Bubble.Content class="whitespace-pre-wrap">{block.text}</Bubble.Content>
										</Bubble.Root>
									{:else if block.type === 'image'}
										<Marker.Root>
											<Marker.Icon><ImageIcon /></Marker.Icon>
											<Marker.Content>Image</Marker.Content>
										</Marker.Root>
									{/if}
								{/each}
								<Message.Footer>{time(item.timestamp)}</Message.Footer>
							</Message.Content>
						</Message.Root>
					{:else}
						<Message.Root>
							<Message.Content class="w-full gap-3">
								{#each segments(item.blocks) as segment, index (index)}
									{#if 'tools' in segment}
										{#if segment.tools.length === 1}
											<Trace.Root>{@render tool(segment.tools[0])}</Trace.Root>
										{:else}
											<Trace.Collapsible>
												<Trace.CollapsibleTrigger>
													<Trace.Line
														status={segment.tools.some((tool) => tool.error) ? 'error' : undefined}
													>
														<Trace.Icon><WrenchIcon /></Trace.Icon>
														<Trace.Title class="truncate">{counts(segment.tools)}</Trace.Title>
													</Trace.Line>
												</Trace.CollapsibleTrigger>
												<Trace.CollapsibleContent>
													<Trace.Root>
														{#each segment.tools as entry, index (index)}
															{@render tool(entry)}
														{/each}
													</Trace.Root>
												</Trace.CollapsibleContent>
											</Trace.Collapsible>
										{/if}
									{:else if segment.block.type === 'image'}
										<Marker.Root>
											<Marker.Icon><ImageIcon /></Marker.Icon>
											<Marker.Content>Image</Marker.Content>
										</Marker.Root>
									{:else}
										<div class="text-sm leading-relaxed whitespace-pre-wrap">{segment.block.text}</div>
									{/if}
								{/each}
								<Message.Footer>{time(item.timestamp)}</Message.Footer>
							</Message.Content>
						</Message.Root>
					{/if}
				</MessageScroller.Item>
			{/each}
		</MessageScroller.Content>
	</MessageScroller.Viewport>
	<MessageScroller.Button />
</MessageScroller.Root>
