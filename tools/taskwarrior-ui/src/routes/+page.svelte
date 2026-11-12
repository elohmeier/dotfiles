<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { Tabs } from 'bits-ui';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import Search from '@lucide/svelte/icons/search';
	import ListTodo from '@lucide/svelte/icons/list-todo';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
	import X from '@lucide/svelte/icons/x';
	import Menu from '@lucide/svelte/icons/menu';
	import Copy from '@lucide/svelte/icons/copy';
	import ChartColumn from '@lucide/svelte/icons/chart-column';
	import { compare, date, dateLabel, shortDateLabel, matches, normalize, relations, sources, text, type Snapshot } from '#lib/tasks.js';

	let snapshot = $state<Snapshot>({ tasks: [], exportedAt: null, error: '' });
	let loading = $state(true);
	let refreshing = $state(false);
	let connected = $state(false);
	let networkError = $state('');
	let sidebarOpen = $state(false);
	let copied = $state(false);
	let searchInput: HTMLInputElement;
	let list: HTMLDivElement;
	const params = $derived(page.url.searchParams);
	const view = $derived(params.get('view') === 'activity' ? 'activity' : 'tasks');
	const filters = $derived({ status: params.get('status') || 'pending', source: params.get('source') || '',
		project: params.get('project') || '', page: params.get('page') || '', q: params.get('q') || '' });
	const selected = $derived(params.get('task') || '');
	const sort = $derived(params.get('sort') || 'urgency');
	const tasks = $derived(snapshot.tasks.map(normalize));
	const activityTasks = $derived(tasks.filter((task) => matches(task, { ...filters, status: 'all' })));
	const shown = $derived(tasks.filter((task) => matches(task, filters)).sort(compare(sort)));
	const current = $derived(tasks.find((task) => task.uuid === selected));
	const related = $derived(current ? relations(current, tasks) : []);
	const statusOptions = $derived(['pending', 'waiting', 'completed', 'deleted',
		...new Set(tasks.map((t) => t.status).filter((s) => !['pending', 'waiting', 'completed', 'deleted'].includes(s))), 'all']);
	const projectTasks = $derived(tasks.filter((task) => matches(task, { ...filters, status: view === 'activity' ? 'all' : filters.status, project: '', page: '', q: '' })));
	const projects = $derived([...new Set(projectTasks.map((t) => t.project).filter(Boolean))].sort((a, b) => a.localeCompare(b)));
	const pages = $derived([...new Set(tasks.map((t) => t.page).filter(Boolean))].sort((a, b) => a.localeCompare(b)));
	const hasFilters = $derived(Boolean(filters.source || filters.project || filters.page || filters.q));
	const error = $derived(snapshot.error || networkError);
	const label = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
	const dateFields = [ ['due', 'Due'], ['scheduled', 'Scheduled'], ['wait', 'Waiting until'], ['start', 'Started'],
		['end', 'Ended in Taskwarrior'], ['entry', 'Entered in Taskwarrior'], ['modified', 'Modified in Taskwarrior'],
		['jiracreatedts', 'Created in Jira'], ['todoistcreatedts', 'Created in Todoist'],
		['todoistupdatedts', 'Updated in Todoist'], ['todoistcompletedts', 'Completed in Todoist'],
		['todoistdeletedts', 'Deleted in Todoist'], ['logseqscheduled', 'Logseq scheduled'], ['logseqdeadline', 'Logseq deadline'], ['logseqdone', 'Logseq done'] ];
	const sourceFields = [ ['jiraid', 'Jira issue'], ['jirastatus', 'Jira status'], ['jiraissuetype', 'Issue type'],
		['jirasummary', 'Jira title'], ['logseqtitle', 'Logseq title'], ['todoistcontent', 'Todoist title'],
		['jirafixversion', 'Fix version'], ['jiraestimate', 'Estimate'], ['logseqstate', 'Logseq state'],
		['logseqpage', 'Logseq page'], ['todoistproject', 'Todoist project'], ['todoistsection', 'Todoist section'],
		['todoistpriority', 'Todoist API priority'], ['todoistlabels', 'Todoist labels'], ['todoistsource', 'Todoist metadata source'] ];

	function nav(changes: Record<string, string | null>, replace = false) {
		const url = new URL(page.url.href);
		for (const [key, value] of Object.entries(changes)) {
			if (value) url.searchParams.set(key, value);
			else url.searchParams.delete(key);
		}
		return goto(url, { replace, reset: false });
	}

	function filter(changes: Record<string, string | null>) {
		nav({ ...changes, task: null });
		if (sidebarOpen) toggleSidebar();
	}

	async function toggleSidebar() {
		sidebarOpen = !sidebarOpen;
		await tick();
		if (sidebarOpen) document.querySelector<HTMLButtonElement>('#task-filters button.active')?.focus();
		else document.querySelector<HTMLButtonElement>('.mobile-menu')?.focus();
	}

	async function accept(value: Snapshot) {
		if (snapshot.exportedAt && value.exportedAt && value.exportedAt < snapshot.exportedAt) return;
		const anchor = list && [...list.querySelectorAll<HTMLElement>('[data-task]')]
			.find((el) => el.getBoundingClientRect().bottom > list.getBoundingClientRect().top);
		const top = anchor?.getBoundingClientRect().top;
		snapshot = value;
		loading = false;
		networkError = '';
		await tick();
		if (anchor && top !== undefined && anchor.isConnected) list.scrollTop += anchor.getBoundingClientRect().top - top;
	}

	async function refresh() {
		if (refreshing) return;
		refreshing = true;
		try {
			const response = await fetch('/api/tasks', { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			await accept(await response.json());
		} catch (cause) {
			networkError = `Could not refresh tasks (${cause instanceof Error ? cause.message : 'connection failed'}).`;
			loading = false;
		} finally { refreshing = false; }
	}

	onMount(() => {
		refresh();
		const events = new EventSource('/api/events');
		events.onopen = () => { connected = true; };
		events.onerror = () => { connected = false; };
		events.addEventListener('snapshot', (event) => accept(JSON.parse(event.data)));
		const poll = setInterval(() => { if (!document.hidden) refresh(); }, 30_000);
		const focus = () => { if (!document.hidden) refresh(); };
		document.addEventListener('visibilitychange', focus);
		return () => { events.close(); clearInterval(poll); document.removeEventListener('visibilitychange', focus); };
	});

	async function copyUuid() {
		if (!current) return;
		await navigator.clipboard.writeText(current.uuid);
		copied = true;
		setTimeout(() => { copied = false; }, 1500);
	}

	async function keydown(event: KeyboardEvent) {
		if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
		const target = event.target as HTMLElement;
		if (target.matches('input, textarea, select') || target.isContentEditable) {
			if (event.key === 'Escape') target.blur();
			return;
		}
		if (event.key === '/') { event.preventDefault(); searchInput?.focus(); }
		else if (event.key === 'Escape') { if (sidebarOpen) toggleSidebar(); else nav({ task: null }); }
		else if (view === 'tasks' && (event.key === 'j' || event.key === 'k') && shown.length) {
			event.preventDefault();
			const index = shown.findIndex((t) => t.uuid === selected);
			const next = shown[Math.max(0, Math.min(shown.length - 1, index + (event.key === 'j' ? 1 : -1)))];
			await nav({ task: next.uuid });
			document.getElementById(`task-${next.uuid}`)?.scrollIntoView({ block: 'nearest' });
		}
	}
</script>

<svelte:window onkeydown={keydown} />

<div class="app" class:has-detail={view === 'tasks' && Boolean(selected)}>
	<aside id="task-filters" class:open={sidebarOpen} aria-label="Task filters">
		<a class="brand" href="/"><span class="brand-icon"><ListTodo size={21} /></span><span>Taskwarrior<small>Local task viewer</small></span></a>
		{#if view === 'tasks'}<nav aria-label="Task status">
			{#each statusOptions as status}
				<button class:active={filters.status === status} aria-pressed={filters.status === status} onclick={() => filter({ status: status === 'pending' ? null : status, project: null, page: null })}>
					<span class="status-dot {status}"></span><span>{status === 'all' ? 'All tasks' : label(status)}</span>
					<span class="count">{status === 'all' ? tasks.length : tasks.filter((t) => t.status === status).length}</span>
				</button>
			{/each}
		</nav>{/if}
		<div class="nav-section"><h2>Sources</h2>
			<button class:active={!filters.source} aria-pressed={!filters.source} onclick={() => filter({ source: null, project: null, page: null })}><span>All sources</span><span class="count">{tasks.length}</span></button>
			{#each sources.filter((source) => tasks.some((t) => t.sources.includes(source))) as source}
				<button class:active={filters.source === source} aria-pressed={filters.source === source} onclick={() => filter({ source, project: null, page: null })}>
					<span class="source-dot {source.toLowerCase()}"></span><span>{source}</span><span class="count">{tasks.filter((t) => t.sources.includes(source)).length}</span>
				</button>
			{/each}
		</div>
		<div class="nav-section projects"><h2>Projects <span>{projects.length}</span></h2>
			<button class:active={!filters.project} aria-pressed={!filters.project} onclick={() => filter({ project: null })}><span>All projects</span><span class="count">{projectTasks.length}</span></button>
			{#each projects as project}
				<button class:active={filters.project === project} aria-pressed={filters.project === project} title={project} onclick={() => filter({ project })}>
					<span class="project-name">{project}</span><span class="count">{projectTasks.filter((t) => t.project === project).length}</span>
				</button>
			{/each}
		</div>
		<footer><span class="readonly">Read only</span><p><kbd>/</kbd> Search {#if view === 'tasks'}<span>·</span> <kbd>j</kbd> <kbd>k</kbd> Navigate{/if}</p></footer>
	</aside>
	{#if sidebarOpen}<button class="scrim" aria-label="Close filters" onclick={toggleSidebar}></button>{/if}

	<main inert={sidebarOpen}>
		<header class="topbar">
			<button class="icon-button mobile-menu" aria-label="Toggle filters" aria-expanded={sidebarOpen} aria-controls="task-filters" onclick={toggleSidebar}><Menu size={20} /></button>
			<div class="search"><Search size={17} /><input bind:this={searchInput} aria-label="Search tasks" placeholder="Search tasks, notes, issue IDs…" value={filters.q} oninput={(e) => nav({ q: e.currentTarget.value || null }, true)} /><kbd>/</kbd></div>
			<div class="connection" class:live={connected && !error} title="CLI changes update automatically"><span></span>{error ? 'Stale' : connected ? 'Live' : 'Reconnecting'}</div>
			<button class="icon-button" class:spinning={refreshing} aria-label="Refresh tasks" title="Refresh tasks" onclick={refresh}><RefreshCw size={17} /></button>
		</header>
		{#if error}<div class="error" role="status">{error} {snapshot.exportedAt ? 'Showing the last successful snapshot.' : ''}<button onclick={refresh}>Retry</button></div>{/if}
		<Tabs.Root class="main-tabs" value={view} onValueChange={(value) => nav({ view: value === 'tasks' ? null : value, task: null })}>
			<div class="view-bar"><Tabs.List class="view-tabs" aria-label="Viewer mode"><Tabs.Trigger value="tasks"><ListTodo size={15} />Tasks</Tabs.Trigger><Tabs.Trigger value="activity"><ChartColumn size={15} />Activity</Tabs.Trigger></Tabs.List></div>
			<Tabs.Content value="tasks" class="tab-panel">
		<div class="workspace">
			<section class="task-list" aria-label="Tasks">
				<div class="list-heading"><div><p class="eyebrow">{filters.source || 'All sources'}</p><h1>{filters.project || (filters.status === 'all' ? 'All tasks' : label(filters.status))}<span>{shown.length}</span></h1></div></div>
				<div class="list-toolbar">
					<label>Sort <select aria-label="Sort tasks" value={sort} onchange={(e) => nav({ sort: e.currentTarget.value === 'urgency' ? null : e.currentTarget.value })}><option value="urgency">Urgency</option><option value="title">Title</option><option value="modified">Recently modified</option><option value="due">Due date</option></select></label>
					{#if pages.length}<select aria-label="Filter by Logseq page" value={filters.page} onchange={(e) => filter({ page: e.currentTarget.value || null })}><option value="">All Logseq pages</option><option value="__missing">No page metadata</option>{#each pages as name}<option value={name}>{name}</option>{/each}</select>{/if}
					{#if hasFilters}<button class="text-button" onclick={() => filter({ q: null, source: null, project: null, page: null })}>Clear filters</button>{/if}
				</div>
				<div class="rows" bind:this={list}>
					{#if loading}<div class="empty"><ListTodo size={30} /><h2>Reading your tasks…</h2></div>
					{:else if !shown.length}<div class="empty"><Search size={30} /><h2>{hasFilters ? 'No matching tasks' : 'No tasks here'}</h2><p>{hasFilters ? 'Try another search or clear your filters.' : `Your ${filters.status === 'all' ? '' : filters.status + ' '}tasks will appear here.`}</p>{#if hasFilters}<button class="text-button" onclick={() => filter({ q: null, source: null, project: null, page: null })}>Clear filters</button>{/if}</div>
					{:else}{#each shown as task (task.uuid)}
						<button id="task-{task.uuid}" data-task={task.uuid} class="task-row" class:selected={selected === task.uuid} aria-pressed={selected === task.uuid} onclick={() => nav({ task: task.uuid })}>
							<span class="row-title">{task.title}</span>
							<span class="row-meta">{#each task.sources as source}<span class="badge source {source.toLowerCase()}">{source}</span>{/each}<span class="row-project">{task.project || 'No project'}</span>{#if task.status !== 'pending'}<span class="row-status">{label(task.status)}</span>{/if}</span>
							{#if task.raw.due}<span class="row-due" class:overdue={task.status === 'pending' && (date(task.raw.due)?.getTime() ?? Infinity) < Date.now()}>Due {shortDateLabel(task.raw.due)}</span>{/if}
						</button>
					{/each}{/if}
				</div>
				<div class="list-footer">{shown.length} of {tasks.length} tasks <span title={snapshot.exportedAt || ''}>{snapshot.exportedAt ? `Read at ${new Date(snapshot.exportedAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}` : 'Waiting for snapshot'}</span></div>
			</section>

			<section class="detail" aria-label="Task details">
				{#if current}
					<div class="detail-bar"><span>Task details</span><div><span class="copy-feedback" role="status">{copied ? 'UUID copied' : ''}</span><button class="icon-button" aria-label="Copy task UUID" title="Copy task UUID" onclick={copyUuid}><Copy size={15} /></button><button class="icon-button" aria-label="Close task details" onclick={() => nav({ task: null })}><X size={19} /></button></div></div>
					<div class="detail-content">
						{#if !shown.some((t) => t.uuid === selected)}<div class="notice">This task is outside the current filters.<button class="text-button" onclick={() => nav({ status: 'all', source: null, project: null, page: null, q: null })}>Show in list</button></div>{/if}
						<div class="detail-badges"><span class="badge state {current.status}">{label(current.status)}</span>{#each current.sources as source}<span class="badge source {source.toLowerCase()}">{source}</span>{/each}</div>
						<h2 class="task-title">{current.title}</h2>
						<p class="detail-project">{current.project || 'No project'}</p>
						{#if current.links.length}<div class="source-links">{#each current.links as link}<a href={link.href} target="_blank" rel="noreferrer">{link.label}<ArrowUpRight size={14} /></a>{/each}</div>{/if}
						{#if current.tags.length}<div class="tags">{#each current.tags as tag}<span>#{tag}</span>{/each}</div>{/if}
						{#if current.tags.includes('todoist_partial')}<p class="notice">Todoist metadata is partial for this task.</p>{/if}
						<section class="detail-section"><h3>Overview</h3><dl><dt>Taskwarrior status</dt><dd>{label(current.status)}</dd><dt>Priority</dt><dd>{text(current.raw, 'priority') || 'Not set'}</dd><dt>Urgency</dt><dd>{current.urgency.toFixed(2)}</dd>{#if current.raw.recur}<dt>Recurrence</dt><dd>{text(current.raw, 'recur')}</dd>{/if}</dl></section>
						{#if current.sources.some((s) => s !== 'Local')}<section class="detail-section"><h3>Source metadata</h3><dl>{#each sourceFields as [key, name]}{#if text(current.raw, key) && (!key.endsWith('title') && !['jirasummary', 'todoistcontent'].includes(key) || text(current.raw, key) !== current.title)}<dt>{name}</dt><dd>{text(current.raw, key)}</dd>{/if}{/each}{#if current.sources.includes('Logseq') && !current.page}<dt>Logseq page</dt><dd class="muted">Not recorded</dd>{/if}</dl></section>{/if}
						{#each [['jiradescription', 'Jira description'], ['todoistdescription', 'Todoist description']] as [key, name]}{#if text(current.raw, key)}<section class="detail-section"><h3>{name}</h3><p class="prose">{text(current.raw, key)}</p></section>{/if}{/each}
						{#if current.annotations.length}<section class="detail-section"><h3>Annotations <span>{current.annotations.length}</span></h3><div class="annotations">{#each current.annotations as annotation}<article><time>{dateLabel(annotation.entry)}</time><p class="prose">{annotation.description}</p></article>{/each}</div></section>{/if}
						{#if related.length}<section class="detail-section"><h3>Related tasks</h3><div class="relations">{#each related as relation}<div><span>{relation.kind}</span>{#if relation.task}<button onclick={() => nav({ task: relation.id })}>{relation.task.title}</button>{:else}<span>{relation.id} · not in local data</span>{/if}</div>{/each}</div></section>{/if}
						<section class="detail-section"><h3>Dates</h3><dl>{#each dateFields as [key, name]}{#if current.raw[key]}<dt>{name}</dt><dd>{dateLabel(current.raw[key])}</dd>{/if}{/each}</dl></section>
						<details class="detail-section"><summary>All attributes</summary><p class="muted">Original exported fields, including source IDs and the import description.</p><pre>{JSON.stringify(current.raw, null, 2)}</pre></details>
					</div>
				{:else}<div class="empty detail-empty"><span class="empty-icon"><ListTodo size={28} /></span><h2>{selected ? 'Task no longer in the snapshot' : 'A little more context'}</h2><p>{selected ? 'It may have been purged from Taskwarrior.' : 'Select a task to read its notes, source details, and related tasks.'}</p>{#if selected}<button class="text-button" onclick={() => nav({ task: null })}>Back to tasks</button>{:else}<span class="keyboard-hint"><kbd>j</kbd> <kbd>k</kbd> to move through tasks</span>{/if}</div>{/if}
			</section>
		</div>
			</Tabs.Content>
			<Tabs.Content value="activity" class="tab-panel">
				{#if loading}<div class="empty"><ListTodo size={28} /><h2>Reading your tasks…</h2></div>
				{:else if view === 'activity'}
					{#await import('#lib/components/activity.svelte')}
						<div class="empty"><ChartColumn size={28} /><h2>Loading activity…</h2></div>
					{:then module}
						<module.default tasks={activityTasks} now={new Date(snapshot.exportedAt || Date.now())} {params} {pages} onchange={nav} onopen={(uuid) => nav({ view: null, status: 'completed', task: uuid })} />
					{/await}
				{/if}
			</Tabs.Content>
		</Tabs.Root>
	</main>
</div>
