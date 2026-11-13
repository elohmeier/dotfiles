<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { Tabs, Dialog } from 'bits-ui';
	import { MediaQuery } from 'svelte/reactivity';
	import { PaneGroup, Pane, PaneResizer } from 'paneforge';
	import SearchChoice from '#lib/components/search-choice.svelte';
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
	import { compare, date, dateLabel, shortDateLabel, matches, normalizeTasks, relations, sources, sourceClass, outcomes, workflowTags, inProject, text, type Snapshot, type Task } from '#lib/tasks.js';

	let snapshot = $state<Snapshot>({ tasks: [], exportedAt: null, error: '' });
	let loading = $state(true);
	let refreshing = $state(false);
	let connected = $state(false);
	let networkError = $state('');
	let sidebarOpen = $state(false);
	let copied = $state(false);
	let clock = $state(Date.now());
	const now = $derived(new Date(clock));
	let searchInput: HTMLInputElement;
	let list: HTMLDivElement;
	const mobile = new MediaQuery('(max-width: 600px)');
	const compact = new MediaQuery('(max-width: 900px)');
	$effect(() => { if (!mobile.current) sidebarOpen = false; });
	const params = $derived(page.url.searchParams);
	const view = $derived(params.get('view') === 'activity' ? 'activity' : 'tasks');
	const filters = $derived({ status: params.get('status') || 'ready', source: params.get('source') || '',
		area: params.get('area') || '', project: params.get('project') || '', scope: params.get('scope') || '',
		page: params.get('page') || '', list: params.get('list') || '', tag: params.get('tag') || '',
		outcome: params.get('outcome') || '', q: params.get('q') || '' });
	const cleared = { q: null, source: null, area: null, project: null, scope: null, page: null, list: null, tag: null, outcome: null };
	const selected = $derived(params.get('task') || '');
	const sort = $derived(params.get('sort') || 'urgency');
	const tasks = $derived(normalizeTasks(snapshot.tasks, now));
	const activityTasks = $derived(tasks.filter((task) => matches(task, { ...filters, status: 'all', outcome: '' })));
	const shown = $derived(tasks.filter((task) => matches(task, filters)).sort(compare(sort)));
	const current = $derived(tasks.find((task) => task.uuid === selected));
	const related = $derived(current ? relations(current, tasks) : []);
	const statusOptions = [
		{ value: 'ready', label: 'Ready' }, { value: 'open', label: 'All open' }, { value: 'waiting', label: 'Hidden until' },
		{ value: 'scheduled', label: 'Scheduled' }, { value: 'blocked', label: 'Blocked' },
		{ value: 'completed', label: 'Closed' }, { value: 'deleted', label: 'Deleted' },
		{ value: 'recurring', label: 'Recurring templates' }, { value: 'all', label: 'All tasks' }
	];
	const stateCount = (status: string) => tasks.filter((task) => matches(task, { status })).length;
	const inboxReview = $derived(filters.status === 'open' && filters.project === 'Inbox' && filters.scope !== 'exact');
	const areaTasks = $derived(tasks.filter((task) => matches(task, { ...filters, status: view === 'activity' ? 'all' : filters.status, area: '', project: '', page: '', q: '', outcome: '', tag: '' })));
	const areas = $derived([...new Set(['Debeka', 'Convexio', 'Family', 'Housing', 'Personal', 'Nerdworks', 'Fraam', 'Inbox', ...areaTasks.map((task) => task.area).filter(Boolean)])]);
	const projectTasks = $derived(areaTasks.filter((task) => !filters.area || task.area === filters.area));
	const projects = $derived([...new Set(projectTasks.flatMap((t) => t.project ? t.project.split('.').map((_, i, parts) => parts.slice(0, i + 1).join('.')) : []))].sort((a, b) => a.localeCompare(b)));
	const pages = $derived([...new Set(tasks.map((t) => t.page).filter(Boolean))].sort((a, b) => a.localeCompare(b)));
	const lists = $derived([...new Set(tasks.map((task) => task.list).filter(Boolean))].sort((a, b) => a.localeCompare(b)));
	const tags = $derived([...new Set([...workflowTags, ...tasks.flatMap((task) => task.tags)])].sort((a, b) => a.localeCompare(b)));
	const activeFilters = $derived([
		{ key: 'q', label: 'Search', value: filters.q }, { key: 'source', label: 'Source', value: filters.source },
		{ key: 'area', label: 'Area', value: filters.area },
		{ key: 'project', label: 'Project', value: filters.project ? `${filters.project}${filters.scope === 'exact' ? ' (exact)' : ' + subprojects'}` : '' },
		{ key: 'page', label: 'Page', value: filters.page === '__missing' ? 'No page metadata' : filters.page },
		{ key: 'list', label: 'Reminders list', value: filters.list }, { key: 'tag', label: 'Tag', value: filters.tag },
		{ key: 'outcome', label: 'Outcome', value: outcomes.find((item) => item.value === filters.outcome)?.label || filters.outcome }
	].filter((item) => item.value));
	const hasFilters = $derived(Boolean(activeFilters.length));
	const projectOptions = $derived([{ value: '__all', label: 'All projects', count: projectTasks.length },
		...projects.map((project) => ({ value: project, label: project.replaceAll('.', ' › '), count: projectTasks.filter((task) => filters.scope === 'exact' ? task.project === project : inProject(task.project, project)).length }))]);
	const pageOptions = $derived([{ value: '__all', label: 'All Logseq pages' }, { value: '__missing', label: 'No page metadata' },
		...pages.map((name) => ({ value: name, label: name }))]);
	const error = $derived(snapshot.error || networkError);
	const label = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
	const stateLabel = (value: string) => statusOptions.find((item) => item.value === value)?.label || label(value);
	const ageDays = (task: Task) => Math.max(0, Math.floor((now.getTime() - (date(task.raw.entry)?.getTime() ?? now.getTime())) / 86_400_000));
	const dueLabel = (task: Task) => task.allDayDue ? `${new Date(`${task.allDayDue}T12:00:00`).toLocaleDateString(undefined, { dateStyle: 'medium' })} (all day)` : dateLabel(task.raw.due);
	const dateFields = [ ['due', 'Due'], ['scheduled', 'Scheduled'], ['wait', 'Waiting until'], ['start', 'Started'],
		['end', 'Ended in Taskwarrior'], ['entry', 'Entered in Taskwarrior'], ['modified', 'Modified in Taskwarrior'],
		['jiracreatedts', 'Created in Jira'], ['todoistcreatedts', 'Created in Todoist'],
		['todoistupdatedts', 'Updated in Todoist'], ['todoistcompletedts', 'Completed in Todoist'],
		['todoistdeletedts', 'Deleted in Todoist'], ['logseqscheduled', 'Logseq scheduled'], ['logseqdeadline', 'Logseq deadline'], ['logseqdone', 'Logseq done'] ];
	dateFields.push(['appleremindersmodified', 'Modified in Reminders']);
	const sourceFields = [ ['jiraid', 'Jira issue'], ['jirastatus', 'Jira status'], ['jiraissuetype', 'Issue type'],
		['jirasummary', 'Jira title'], ['logseqtitle', 'Logseq title'], ['todoistcontent', 'Todoist title'],
		['jirafixversion', 'Fix version'], ['jiraestimate', 'Estimate'], ['logseqstate', 'Logseq state'],
		['logseqpage', 'Logseq page'], ['todoistproject', 'Todoist project'], ['todoistsection', 'Todoist section'],
		['todoistpriority', 'Todoist API priority'], ['todoistlabels', 'Todoist labels'], ['todoistsource', 'Todoist metadata source'],
		['applereminderslist', 'Original Reminders list'], ['applereminderstitle', 'Reminder title'], ['appleremindersurl', 'Reminder attachment URL'] ];

	function nav(changes: Record<string, string | null>, replace = false) {
		const url = new URL(page.url.href);
		for (const [key, value] of Object.entries(changes)) {
			if (value) url.searchParams.set(key, value);
			else url.searchParams.delete(key);
		}
		return goto(url, { replace, reset: false });
	}

	function filter(changes: Record<string, string | null>) {
		nav({ ...changes, task: null, period: null });
		sidebarOpen = false;
	}

	async function accept(value: Snapshot) {
		if (snapshot.exportedAt && value.exportedAt && value.exportedAt < snapshot.exportedAt) return;
		const anchor = list && [...list.querySelectorAll<HTMLElement>('[data-task]')]
			.find((el) => el.getBoundingClientRect().bottom > list.getBoundingClientRect().top);
		const top = anchor?.getBoundingClientRect().top;
		snapshot = value;
		clock = Date.now();
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
		const poll = setInterval(() => { clock = Date.now(); if (!document.hidden) refresh(); }, 30_000);
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
		if (target.closest('[data-dialog-content], [data-popover-content], [data-select-content], [data-combobox-content]')) return;
		if (target.matches('input, textarea, select') || target.isContentEditable) {
			if (event.key === 'Escape') target.blur();
			return;
		}
		if (event.key === '/') { event.preventDefault(); searchInput?.focus(); }
		else if (event.key === 'Escape') nav({ task: null });
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

{#snippet sidebarContent()}
		<a class="brand" href="/" onclick={() => { sidebarOpen = false; }}><span class="brand-icon"><ListTodo size={21} /></span><span>Taskwarrior<small>Local task viewer</small></span></a>
		{#if view === 'tasks'}<nav aria-label="Task status">
			{#each statusOptions.filter((item) => !['scheduled', 'blocked', 'recurring'].includes(item.value) || stateCount(item.value) || filters.status === item.value) as status}
				<button class:active={filters.status === status.value && !inboxReview} aria-pressed={filters.status === status.value && !inboxReview} onclick={() => filter({ status: status.value === 'ready' ? null : status.value, outcome: status.value === 'completed' ? filters.outcome : null })}>
					<span class="status-dot {status.value}"></span><span>{status.label}</span>
					<span class="count">{stateCount(status.value)}</span>
				</button>
			{/each}
			<button class:active={inboxReview} aria-pressed={inboxReview} onclick={() => { filter({ ...cleared, view: null, status: 'open', project: 'Inbox', sort: 'oldest' }); }}><span class="status-dot"></span><span>Inbox review</span><span class="count">{tasks.filter((task) => task.open && inProject(task.project, 'Inbox')).length}</span></button>
		</nav>{/if}
		<div class="nav-section"><h2>Sources</h2>
			<button class:active={!filters.source} aria-pressed={!filters.source} onclick={() => filter({ source: null, project: null, page: null, list: null })}><span>All sources</span><span class="count">{tasks.length}</span></button>
			{#each sources.filter((source) => tasks.some((t) => t.sources.includes(source))) as source}
				<button class:active={filters.source === source} aria-pressed={filters.source === source} onclick={() => filter({ source, project: null, page: null, list: null })}>
					<span class="source-dot {sourceClass(source)}"></span><span>{source}</span><span class="count">{tasks.filter((t) => t.sources.includes(source)).length}</span>
				</button>
			{/each}
		</div>
		<div class="nav-section projects"><h2>Responsibility</h2>
			<SearchChoice label="Area" value={filters.area || '__all'} options={[{ value: '__all', label: 'All areas', count: areaTasks.length }, ...areas.map((area) => ({ value: area, label: area, count: areaTasks.filter((task) => task.area === area).length }))]} onchange={(value) => filter({ area: value === '__all' ? null : value, project: null, scope: null })} />
			<SearchChoice label="Project" value={filters.project || '__all'} options={projectOptions} onchange={(value) => filter({ project: value === '__all' ? null : value })} />
			{#if filters.project}<label class="subproject-toggle"><input type="checkbox" checked={filters.scope !== 'exact'} onchange={(event) => filter({ scope: event.currentTarget.checked ? null : 'exact' })} />Include subprojects</label>{/if}
		</div>
		<div class="nav-section"><h2>Workflow</h2>
			<SearchChoice label="Tag" value={filters.tag || '__all'} options={[{ value: '__all', label: 'All tags' }, ...tags.map((tag) => ({ value: tag, label: `#${tag}`, count: tasks.filter((task) => task.open && task.tags.includes(tag)).length }))]} onchange={(value) => filter({ tag: value === '__all' ? null : value })} />
			<div class="workflow-shortcuts">{#each workflowTags as tag}<button class:active={filters.tag === tag} aria-pressed={filters.tag === tag} onclick={() => filter({ tag: filters.tag === tag ? null : tag, status: 'open', outcome: null })}>#{tag}</button>{/each}</div>
			{#if view === 'activity' || ['completed', 'all'].includes(filters.status) || filters.outcome}<SearchChoice label="Closure outcome" value={filters.outcome || '__all'} options={[{ value: '__all', label: 'All closure outcomes' }, ...outcomes]} onchange={(value) => filter({ outcome: value === '__all' ? null : value, status: 'completed' })} />{/if}
		</div>
		{#if lists.length}<div class="nav-section"><h2>Source context</h2><SearchChoice label="Reminders list" value={filters.list || '__all'} options={[{ value: '__all', label: 'All Reminders lists' }, ...lists.map((list) => ({ value: list, label: list }))]} onchange={(value) => filter({ list: value === '__all' ? null : value })} /></div>{/if}
		<footer><span class="readonly">Read only</span><p><kbd>/</kbd> Search {#if view === 'tasks'}<span>·</span> <kbd>j</kbd> <kbd>k</kbd> Navigate{/if}</p></footer>
{/snippet}

{#snippet taskList()}
			<section class="task-list" aria-label="Tasks">
				<div class="list-heading"><div><p class="eyebrow">{filters.area || filters.source || 'All sources'}</p><h1>{inboxReview ? 'Inbox review' : filters.project || stateLabel(filters.status)}<span>{shown.length}</span></h1>{#if inboxReview}<p class="review-intro">Unclassified actions with their original source context.</p>{/if}</div></div>
				<div class="list-toolbar">
					<label>Sort <select aria-label="Sort tasks" value={sort} onchange={(e) => nav({ sort: e.currentTarget.value === 'urgency' ? null : e.currentTarget.value })}><option value="urgency">Urgency</option><option value="title">Title</option><option value="modified">Recently modified</option><option value="oldest">Oldest first</option><option value="followup">Follow-up date</option><option value="due">Due date</option></select></label>
					{#if pages.length}<SearchChoice label="Logseq page" value={filters.page || '__all'} options={pageOptions} onchange={(value) => filter({ page: value === '__all' ? null : value })} />{/if}
				</div>
				<div class="rows" bind:this={list}>
					{#if loading}<div class="empty"><ListTodo size={30} /><h2>Reading your tasks…</h2></div>
					{:else if !shown.length}<div class="empty"><Search size={30} /><h2>{hasFilters ? 'No matching tasks' : 'No tasks here'}</h2><p>{hasFilters ? 'Try another search or clear your filters.' : `Tasks in this view will appear here.`}</p>{#if hasFilters}<button class="text-button" onclick={() => filter(cleared)}>Clear filters</button>{/if}</div>
					{:else}{#each shown as task (task.uuid)}
						<button id="task-{task.uuid}" data-task={task.uuid} class="task-row" class:selected={selected === task.uuid} aria-pressed={selected === task.uuid} onclick={() => nav({ task: task.uuid })}>
							<span class="row-title">{task.title}</span>
							<span class="row-meta">{#each task.sources as source}<span class="badge source {sourceClass(source)}">{source}</span>{/each}<span class="row-project">{task.project || 'No project'}</span>{#if !task.ready}<span class="row-status">{task.status === 'completed' ? outcomes.find((item) => item.value === task.outcome)?.label : task.workflow}</span>{/if}</span>
							{#if task.tags.some((tag) => workflowTags.includes(tag)) || task.waitingFor}<span class="row-workflow">{#each task.tags.filter((tag) => workflowTags.includes(tag)) as tag}<span>#{tag}</span>{/each}{#if task.waitingFor}<span>Waiting for {task.waitingFor}</span>{/if}</span>{/if}
							{#if inboxReview}<span class="row-context">{task.list || task.page || 'Source context not recorded'}{#if task.sourceProject}<span> · Source project: {task.sourceProject}</span>{/if}</span>{#if task.context}<span class="row-ancestor">{task.context}</span>{/if}<span class="row-review-meta"><span>Priority {text(task.raw, 'priority') || 'not set'}</span><span title="Age since the Taskwarrior entry date">{ageDays(task)} days old</span></span>{/if}
							{#if task.hidden}<span class="row-followup">Hidden until {shortDateLabel(task.raw.wait)}</span>{/if}
							{#if task.raw.scheduled}<span class="row-followup">{task.tags.includes('delegated') ? 'Follow up' : 'Scheduled'} {shortDateLabel(task.raw.scheduled)}</span>{/if}
							{#if task.raw.due}<span class="row-due" class:overdue={task.open && (date(task.raw.due)?.getTime() ?? Infinity) < now.getTime()}>Due {shortDateLabel(task.allDayDue ? `${task.allDayDue}T12:00:00` : task.raw.due)}</span>{/if}
						</button>
					{/each}{/if}
				</div>
				<div class="list-footer">{shown.length} of {tasks.length} tasks <span title={snapshot.exportedAt || ''}>{snapshot.exportedAt ? `Read at ${new Date(snapshot.exportedAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}` : 'Waiting for snapshot'}</span></div>
			</section>
{/snippet}

{#snippet taskDetails()}
			<section class="detail" aria-label="Task details">
				{#if current}
					<div class="detail-bar"><span>Task details</span><div><span class="copy-feedback" role="status">{copied ? 'UUID copied' : ''}</span><button class="icon-button" aria-label="Copy task UUID" title="Copy task UUID" onclick={copyUuid}><Copy size={15} /></button><button class="icon-button" aria-label="Close task details" onclick={() => nav({ task: null })}><X size={19} /></button></div></div>
					<div class="detail-content">
						{#if !shown.some((t) => t.uuid === selected)}<div class="notice">This task is outside the current filters.<button class="text-button" onclick={() => nav({ ...cleared, status: 'all' })}>Show in list</button></div>{/if}
						<div class="detail-badges"><span class="badge state {current.status}">{current.status === 'completed' ? 'Closed' : current.workflow}</span>{#each current.sources as source}<span class="badge source {sourceClass(source)}">{source}</span>{/each}</div>
						<h2 class="task-title">{current.title}</h2>
						<p class="detail-project">{current.project || 'No project'}</p>
						{#if current.links.length}<div class="source-links">{#each current.links as link}<a href={link.href} target="_blank" rel="noreferrer">{link.label}<ArrowUpRight size={14} /></a>{/each}</div>{/if}
						{#if current.tags.length}<div class="tags">{#each current.tags as tag}<button aria-label={`Filter by tag ${tag}`} onclick={() => filter({ tag })}>#{tag}</button>{/each}</div>{/if}
						{#if current.tags.includes('todoist_partial')}<p class="notice">Todoist metadata is partial for this task.</p>{/if}
						<section class="detail-section"><h3>Workflow</h3><dl><dt>State</dt><dd>{stateLabel(current.workflow)}</dd>{#if current.waitingFor}<dt>Waiting for</dt><dd>{current.waitingFor}</dd>{/if}{#if current.followUp}<dt>Follow up</dt><dd>{dateLabel(current.followUp.toISOString())}</dd>{/if}{#if current.status === 'completed'}<dt>Closure outcome</dt><dd>{outcomes.find((item) => item.value === current.outcome)?.label}</dd>{/if}</dl></section>
						{#if current.context || current.sourceProject}<section class="detail-section"><h3>Source context</h3>{#if current.context}<p class="prose">{current.context}</p>{/if}{#if current.sourceProject}<p class="source-project">Source project: {current.sourceProject}</p>{/if}</section>{/if}
						<section class="detail-section"><h3>Overview</h3><dl><dt>Taskwarrior status</dt><dd>{label(current.status)}</dd><dt>Priority</dt><dd>{text(current.raw, 'priority') || 'Not set'}</dd><dt>Urgency</dt><dd>{current.urgency.toFixed(2)}</dd>{#if current.raw.recur}<dt>Recurrence</dt><dd>{text(current.raw, 'recur')}</dd>{/if}</dl></section>
						{#if current.sources.some((s) => s !== 'Local')}<section class="detail-section"><h3>Source metadata</h3><dl>{#each sourceFields as [key, name]}{#if text(current.raw, key) && (!key.endsWith('title') && !['jirasummary', 'todoistcontent'].includes(key) || text(current.raw, key) !== current.title)}<dt>{name}</dt><dd>{text(current.raw, key)}</dd>{/if}{/each}{#if current.sources.includes('Logseq') && !current.page}<dt>Logseq page</dt><dd class="muted">Not recorded</dd>{/if}</dl></section>{/if}
						{#each [['jiradescription', 'Jira description'], ['todoistdescription', 'Todoist description']] as [key, name]}{#if text(current.raw, key)}<section class="detail-section"><h3>{name}</h3><p class="prose">{text(current.raw, key)}</p></section>{/if}{/each}
						{#if current.annotations.length}<section class="detail-section"><h3>Annotations <span>{current.annotations.length}</span></h3><div class="annotations">{#each current.annotations as annotation}<article><time>{dateLabel(annotation.entry)}</time><p class="prose">{annotation.description}</p></article>{/each}</div></section>{/if}
						{#if related.length}<section class="detail-section"><h3>Related tasks</h3><div class="relations">{#each related as relation}<div><span>{relation.kind}</span>{#if relation.task}<button onclick={() => nav({ task: relation.id })}>{relation.task.title}</button>{:else}<span>{relation.id} · not in local data</span>{/if}</div>{/each}</div></section>{/if}
						<section class="detail-section"><h3>Dates</h3><dl>{#each dateFields as [key, name]}{#if current.raw[key]}<dt>{name}</dt><dd>{key === 'due' ? dueLabel(current) : dateLabel(current.raw[key])}</dd>{/if}{/each}</dl></section>
						<details class="detail-section"><summary>All attributes</summary><p class="muted">Original exported fields, including source IDs and the import description.</p><pre>{JSON.stringify(current.raw, null, 2)}</pre></details>
					</div>
				{:else}<div class="empty detail-empty"><span class="empty-icon"><ListTodo size={28} /></span><h2>{selected ? 'Task no longer in the snapshot' : 'A little more context'}</h2><p>{selected ? 'It may have been purged from Taskwarrior.' : 'Select a task to read its notes, source details, and related tasks.'}</p>{#if selected}<button class="text-button" onclick={() => nav({ task: null })}>Back to tasks</button>{:else}<span class="keyboard-hint"><kbd>j</kbd> <kbd>k</kbd> to move through tasks</span>{/if}</div>{/if}
			</section>
{/snippet}

<Dialog.Root bind:open={sidebarOpen}>
<div class="app" class:has-detail={view === 'tasks' && Boolean(selected)}>
	{#if !mobile.current}<aside class="sidebar" aria-label="Task filters">{@render sidebarContent()}</aside>{/if}

	<main>
		<header class="topbar">
			<Dialog.Trigger class="icon-button mobile-menu" aria-label="Toggle filters"><Menu size={20} /></Dialog.Trigger>
			<div class="search input-group"><Search size={17} /><input bind:this={searchInput} aria-label="Search tasks" placeholder="Search tasks, notes, issue IDs…" value={filters.q} oninput={(e) => nav({ q: e.currentTarget.value || null }, true)} />{#if filters.q}<button class="icon-button clear-search" aria-label="Clear search" onclick={async () => { await nav({ q: null }, true); searchInput.focus(); }}><X size={15} /></button>{:else}<kbd>/</kbd>{/if}</div>
			<div class="connection" class:live={connected && !error} title="CLI changes update automatically"><span></span>{error ? 'Stale' : connected ? 'Live' : 'Reconnecting'}</div>
			<button class="icon-button" class:spinning={refreshing} aria-label="Refresh tasks" title="Refresh tasks" onclick={refresh}><RefreshCw size={17} /></button>
		</header>
		{#if error}<div class="error" role="status">{error} {snapshot.exportedAt ? 'Showing the last successful snapshot.' : ''}<button onclick={refresh}>Retry</button></div>{/if}
		<Tabs.Root class="main-tabs" value={view} onValueChange={(value) => nav({ view: value === 'tasks' ? null : value, task: null })}>
			<div class="view-bar"><Tabs.List class="view-tabs" aria-label="Viewer mode"><Tabs.Trigger value="tasks"><ListTodo size={15} />Tasks</Tabs.Trigger><Tabs.Trigger value="activity"><ChartColumn size={15} />Activity</Tabs.Trigger></Tabs.List></div>
			{#if activeFilters.length}<div class="filter-bar" aria-label="Active filters">{#each activeFilters as item}<button class="filter-chip" aria-label={`Remove ${item.label.toLowerCase()} filter`} onclick={() => filter({ [item.key]: null })}><span>{item.label}: <strong>{item.value}</strong></span><X size={12} /></button>{/each}<button class="text-button" onclick={() => filter(cleared)}>Clear filters</button></div>{/if}
			<Tabs.Content value="tasks" class="tab-panel">
				{#if compact.current}
					<div class="workspace compact-workspace"><div class="list-pane" hidden={Boolean(selected)}>{@render taskList()}</div><div class="detail-pane" hidden={!selected}>{@render taskDetails()}</div></div>
				{:else}
					<PaneGroup direction="horizontal" autoSaveId="taskwarrior-viewer-panes" class="workspace resizable-workspace">
						<Pane id="task-list-pane" defaultSize={52} minSize={25} class="list-pane">{@render taskList()}</Pane>
						<PaneResizer class="pane-resizer" aria-label="Resize task list and details"><span></span></PaneResizer>
						<Pane id="task-detail-pane" defaultSize={48} minSize={25} class="detail-pane">{@render taskDetails()}</Pane>
					</PaneGroup>
				{/if}
			</Tabs.Content>
			<Tabs.Content value="activity" class="tab-panel">
				{#if loading}<div class="empty"><ListTodo size={28} /><h2>Reading your tasks…</h2></div>
				{:else if view === 'activity'}
					{#await import('#lib/components/activity.svelte')}
						<div class="empty"><ChartColumn size={28} /><h2>Loading activity…</h2></div>
					{:then module}
						<module.default tasks={activityTasks} {now} {params} {pages} onchange={nav} onopen={(uuid) => nav({ view: null, status: 'completed', task: uuid })} />
					{/await}
				{/if}
			</Tabs.Content>
		</Tabs.Root>
	</main>
</div>

	{#if mobile.current}<Dialog.Portal><Dialog.Overlay class="sheet-overlay" /><Dialog.Content class="sidebar filter-sheet"><Dialog.Title class="sr-only">Task filters</Dialog.Title><Dialog.Description class="sr-only">Filter the read-only task viewer by status, source and project.</Dialog.Description><Dialog.Close class="icon-button sheet-close" aria-label="Close filters"><X size={19} /></Dialog.Close>{@render sidebarContent()}</Dialog.Content></Dialog.Portal>{/if}
</Dialog.Root>
