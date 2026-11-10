<script lang="ts">
	import FolderGit2Icon from '@lucide/svelte/icons/folder-git-2';
	import FolderXIcon from '@lucide/svelte/icons/folder-x';
	import GitBranchIcon from '@lucide/svelte/icons/git-branch';
	import GitForkIcon from '@lucide/svelte/icons/git-fork';
	import LayersIcon from '@lucide/svelte/icons/layers';
	import MessagesSquareIcon from '@lucide/svelte/icons/messages-square';
	import SearchIcon from '@lucide/svelte/icons/search';
	import SparklesIcon from '@lucide/svelte/icons/sparkles';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Badge } from '#lib/components/ui/badge/index.js';
	import * as CodeBlock from '#lib/components/ui/code-block/index.js';
	import * as Empty from '#lib/components/ui/empty/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import { Kbd } from '#lib/components/ui/kbd/index.js';
	import * as Marker from '#lib/components/ui/marker/index.js';
	import * as MessageScroller from '#lib/components/ui/message-scroller/index.js';
	import * as Sidebar from '#lib/components/ui/sidebar/index.js';
	import { Skeleton } from '#lib/components/ui/skeleton/index.js';
	import * as ToggleGroup from '#lib/components/ui/toggle-group/index.js';
	import Transcript from '#lib/components/transcript.svelte';
	import { ago, day, get, home, type Detail, type Session, type Workspace } from '#lib/api.js';

	const params = $derived(page.url.searchParams);
	const workspace = $derived(params.get('w'));
	const query = $derived(params.get('q') ?? '');
	const agent = $derived(params.get('agent') ?? '');
	const sort = $derived(params.get('sort') ?? '');
	const selected = $derived(params.get('s'));
	const line = $derived(params.get('line'));
	const pickup = $derived(!workspace && !query && !params.has('all'));

	let workspaces = $state<Workspace[]>([]);
	let filter = $state('');
	let sessions = $state<Session[] | null>(null);
	let detail = $state<Detail | null>(null);
	let search = $state<HTMLInputElement | null>(null);
	let text = $state(page.url.searchParams.get('q') ?? '');

	const current = $derived(workspaces.find((w) => w.key === workspace));
	const shown = $derived(
		workspaces.filter((w) => !filter || w.key.toLowerCase().includes(filter.toLowerCase()))
	);
	const refs = $derived(new Set(sessions?.map((s) => s.ref)));

	function nav(changes: Record<string, string | null>, replace = false) {
		const url = new URL(page.url.href);
		for (const [key, value] of Object.entries(changes)) {
			if (value) url.searchParams.set(key, value);
			else url.searchParams.delete(key);
		}
		goto(url, { replace, reset: false });
	}

	const open = (session: Session) =>
		nav({ s: session.ref, line: session.match_line == null ? null : String(session.match_line) });

	async function loadWorkspaces() {
		workspaces = await get<Workspace[]>('workspaces');
	}

	$effect(() => {
		loadWorkspaces();
	});

	$effect(() => {
		const args = { workspace, q: query, agent, sort };
		if (pickup) return;
		sessions = null;
		get<Session[]>('sessions', args).then((rows) => {
			if (JSON.stringify(args) === JSON.stringify({ workspace, q: query, agent, sort })) sessions = rows;
		});
	});

	$effect(() => {
		const args = { ref: selected, line };
		detail = null;
		if (!selected) return;
		get<Detail>('session', args).then((value) => {
			if (args.ref === selected) detail = value;
		});
	});

	let timer: ReturnType<typeof setTimeout>;
	function type() {
		clearTimeout(timer);
		timer = setTimeout(() => nav({ q: text.trim() || null, s: null, line: null }, true), 250);
	}

	function keydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (target.matches('input, textarea')) {
			if (event.key === 'Escape') target.blur();
			return;
		}
		if (event.key === '/') {
			event.preventDefault();
			search?.focus();
		} else if ((event.key === 'j' || event.key === 'k') && sessions?.length) {
			const index = sessions.findIndex((s) => s.ref === selected);
			const next = sessions[Math.max(0, Math.min(sessions.length - 1, index + (event.key === 'j' ? 1 : -1)))];
			open(next);
			document.getElementById(next.ref)?.scrollIntoView({ block: 'nearest' });
		} else if (event.key === 'y' && detail) {
			navigator.clipboard.writeText(detail.session.resume);
		}
	}
</script>

<svelte:window onkeydown={keydown} onfocus={loadWorkspaces} />

{#snippet meta(session: Session)}
	<span class="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
		<Badge variant="outline" class="px-1.5 font-mono text-[10px]">
			{session.store.includes('sandbox') ? `${session.agent}·sbx` : session.agent}
		</Badge>
		{#if session.branch}
			<span class="flex min-w-0 items-center gap-0.5 truncate"><GitBranchIcon class="size-3 shrink-0" />{session.branch}</span>
		{/if}
		<span class="shrink-0">· {ago(session.updated)} · {session.message_count} msgs</span>
	</span>
{/snippet}

<Sidebar.Provider>
	<Sidebar.Root>
		<Sidebar.Header>
			<div class="flex items-center gap-2 px-2 py-1 font-semibold">
				<MessagesSquareIcon class="size-4" /> Agent sessions
			</div>
			<Sidebar.Input placeholder="Filter workspaces…" bind:value={filter} />
		</Sidebar.Header>
		<Sidebar.Content>
			<Sidebar.Group>
				<Sidebar.Menu>
					<Sidebar.MenuItem>
						<Sidebar.MenuButton isActive={pickup} onclick={() => goto('?')}>
							<SparklesIcon /> <span>Pick up</span>
						</Sidebar.MenuButton>
					</Sidebar.MenuItem>
					<Sidebar.MenuItem>
						<Sidebar.MenuButton
							isActive={!pickup && !workspace}
							onclick={() => nav({ all: '1', w: null, s: null, line: null })}
						>
							<LayersIcon /> <span>All sessions</span>
						</Sidebar.MenuButton>
					</Sidebar.MenuItem>
				</Sidebar.Menu>
			</Sidebar.Group>
			<Sidebar.Group>
				<Sidebar.GroupLabel>Workspaces · {workspaces.length}</Sidebar.GroupLabel>
				<Sidebar.Menu>
					{#each shown as w (w.key)}
						<Sidebar.MenuItem>
							<Sidebar.MenuButton
								isActive={w.key === workspace}
								class={w.exists ? '' : 'opacity-50'}
								title={home(w.key)}
								onclick={() => nav({ w: w.key, all: null, s: null, line: null })}
							>
								{#if w.exists}<FolderGit2Icon />{:else}<FolderXIcon />{/if}
								<span>{w.name}</span>
							</Sidebar.MenuButton>
							<Sidebar.MenuBadge class="text-muted-foreground">{ago(w.updated)}</Sidebar.MenuBadge>
						</Sidebar.MenuItem>
					{/each}
				</Sidebar.Menu>
			</Sidebar.Group>
		</Sidebar.Content>
	</Sidebar.Root>

	<Sidebar.Inset class="flex h-svh min-w-0 flex-col overflow-hidden">
		<header class="flex shrink-0 items-center gap-3 border-b px-4 py-2">
			<Sidebar.Trigger />
			<div class="relative w-full max-w-md">
				<SearchIcon class="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
				<Input
					bind:ref={search}
					bind:value={text}
					oninput={type}
					class="pl-8"
					placeholder="Search conversations… (b:branch m:model store:codex:sandbox)"
				/>
			</div>
			<ToggleGroup.Root
				type="single"
				size="sm"
				variant="outline"
				value={agent}
				onValueChange={(value) => nav({ agent: value || null, s: null, line: null })}
			>
				{#each ['claude', 'codex', 'pi'] as name (name)}
					<ToggleGroup.Item value={name}>{name}</ToggleGroup.Item>
				{/each}
			</ToggleGroup.Root>
			{#if query}
				<ToggleGroup.Root
					type="single"
					size="sm"
					variant="outline"
					value={sort || 'relevance'}
					onValueChange={(value) => value && nav({ sort: value === 'recent' ? value : null }, true)}
				>
					<ToggleGroup.Item value="relevance">Relevance</ToggleGroup.Item>
					<ToggleGroup.Item value="recent">Recent</ToggleGroup.Item>
				</ToggleGroup.Root>
			{/if}
			<span class="ml-auto hidden gap-1 text-xs text-muted-foreground lg:flex">
				<Kbd>/</Kbd> search <Kbd>j</Kbd><Kbd>k</Kbd> move <Kbd>y</Kbd> copy command
			</span>
		</header>

		{#if pickup}
			<div class="min-h-0 flex-1 overflow-y-auto p-6">
				<h1 class="mb-1 text-lg font-semibold">Pick up where you left off</h1>
				<p class="mb-6 text-sm text-muted-foreground">The latest session of each workspace.</p>
				<div class="grid grid-cols-[repeat(auto-fill,minmax(22rem,1fr))] gap-4">
					{#each shown.slice(0, 60) as w (w.key)}
						<button
							class="flex flex-col gap-2 rounded-xl border bg-card p-4 text-left transition-colors hover:bg-accent/50"
							onclick={() => nav({ w: w.key, s: w.latest.ref })}
						>
							<span class="flex items-center gap-2">
								{#if w.exists}<FolderGit2Icon class="size-4 shrink-0" />{:else}<FolderXIcon class="size-4 shrink-0" />{/if}
								<span class="truncate font-medium">{w.name}</span>
								<span class="ml-auto shrink-0 text-xs text-muted-foreground">{w.count} {w.count === 1 ? "session" : "sessions"}</span>
							</span>
							<span class="truncate text-xs text-muted-foreground">{home(w.key)}</span>
							<span class="line-clamp-2 text-sm font-medium">{w.latest.title || 'Untitled'}</span>
							<span class="line-clamp-3 text-sm text-muted-foreground">{w.latest.last_reply}</span>
							{@render meta(w.latest)}
						</button>
					{/each}
				</div>
			</div>
		{:else}
			<div class="flex min-h-0 flex-1">
				<div class="flex w-96 shrink-0 flex-col border-r">
					<div class="border-b px-4 py-3">
						<div class="truncate font-medium">{current?.name ?? 'All sessions'}</div>
						<div class="truncate text-xs text-muted-foreground">
							{current ? home(current.key) : 'Every workspace'}
							{#if sessions} · {sessions.length} {sessions.length === 1 ? "session" : "sessions"}{/if}
						</div>
					</div>
					<div class="min-h-0 flex-1 overflow-y-auto">
						{#if !sessions}
							{#each { length: 6 }, index (index)}
								<div class="space-y-2 border-b p-4">
									<Skeleton class="h-4 w-3/4" />
									<Skeleton class="h-3 w-1/2" />
								</div>
							{/each}
						{:else if !sessions.length}
							<Empty.Root>
								<Empty.Header>
									<Empty.Title>No sessions</Empty.Title>
									<Empty.Description>Nothing matches this search.</Empty.Description>
								</Empty.Header>
							</Empty.Root>
						{/if}
						{#each sessions ?? [] as session, index (session.ref)}
							{#if (!query || sort) && (index === 0 || day(sessions![index - 1].updated) !== day(session.updated))}
								<Marker.Root variant="separator" class="px-4 pt-3">
									<Marker.Content>{day(session.updated)}</Marker.Content>
								</Marker.Root>
							{/if}
							{@const child = !query && refs.has(session.parent)}
							<button
								id={session.ref}
								class={[
									'flex w-full flex-col gap-1 border-b px-4 py-3 text-left transition-colors hover:bg-accent/50',
									session.ref === selected && 'bg-accent',
									child && 'pl-8'
								]}
								onclick={() => open(session)}
							>
								<span class="flex items-center gap-1.5">
									{#if session.parent}<GitForkIcon class="size-3.5 shrink-0 text-muted-foreground" />{/if}
									<span class="line-clamp-2 text-sm font-medium">{session.title || 'Untitled'}</span>
								</span>
								{#if !workspace}
									<span class="truncate text-xs text-muted-foreground">{home(session.workspace)}</span>
								{/if}
								{@render meta(session)}
								{#if query && session.snippet}
									<span class="line-clamp-3 text-xs text-muted-foreground">
										{#each session.snippet.split(/(\x02[^\x03]*\x03)/) as part, index (index)}
											{#if part.startsWith('\x02')}
												<mark class="rounded-sm bg-yellow-200 px-0.5 text-foreground dark:bg-yellow-500/30">{part.slice(1, -1)}</mark>
											{:else}{part}{/if}
										{/each}
									</span>
								{/if}
							</button>
						{/each}
					</div>
				</div>

				<div class="flex min-w-0 flex-1 flex-col">
					{#if detail}
						{@const s = detail.session}
						<div class="flex shrink-0 flex-col gap-2 border-b px-6 py-3">
							<div class="flex items-start gap-3">
								<h2 class="line-clamp-2 flex-1 font-semibold">{s.title || 'Untitled'}</h2>
								{#if s.model}<Badge variant="secondary">{s.model}</Badge>{/if}
							</div>
							{@render meta(s)}
							{#if s.parent}
								<button
									class="w-fit text-xs text-muted-foreground hover:underline"
									onclick={() => nav({ s: s.parent, line: null })}
								>
									↳ {s.kind || 'continuation'} of {s.parent}
								</button>
							{/if}
							{#if !s.cwd_exists}
								<p class="text-xs text-destructive">Directory no longer exists: {s.cwd}</p>
							{/if}
							<CodeBlock.Root size="sm">
								<CodeBlock.Header>
									<CodeBlock.Title>Resume</CodeBlock.Title>
									<CodeBlock.Actions>
										<CodeBlock.CopyButton value={s.resume} />
									</CodeBlock.Actions>
								</CodeBlock.Header>
								<CodeBlock.Content wrap code={s.resume} />
							</CodeBlock.Root>
						</div>
						{#key s.ref}
							<MessageScroller.Provider defaultScrollPosition={detail.focus ? 'start' : 'last-anchor'}>
								<Transcript messages={detail.messages} focus={detail.focus} />
							</MessageScroller.Provider>
						{/key}
					{:else if selected}
						<div class="space-y-3 p-6">
							<Skeleton class="h-5 w-2/3" />
							<Skeleton class="h-16 w-full" />
							<Skeleton class="h-40 w-full" />
						</div>
					{:else}
						<Empty.Root class="flex-1">
							<Empty.Header>
								<Empty.Media variant="icon"><MessagesSquareIcon /></Empty.Media>
								<Empty.Title>Select a session</Empty.Title>
								<Empty.Description>Read the transcript and copy the command to continue it.</Empty.Description>
							</Empty.Header>
						</Empty.Root>
					{/if}
				</div>
			</div>
		{/if}
	</Sidebar.Inset>
</Sidebar.Provider>
