export type RawTask = Record<string, unknown> & {
	uuid: string;
	status: string;
	description: string;
};

export type Snapshot = { tasks: RawTask[]; exportedAt: string | null; error: string };
export type Task = ReturnType<typeof normalize>;
export const sources = ['Logseq', 'Apple Reminders', 'Todoist', 'Jira', 'Local'];
export const sourceClass = (source: string) => source.toLowerCase().replaceAll(' ', '-');
export const workflowTags = ['next', 'delegated', 'verify', 'steuer'];
export const outcomes = [
	{ value: 'done', label: 'Done', color: 'var(--green)' },
	{ value: 'dropped', label: 'Dropped', color: 'var(--orange)' },
	{ value: 'merged', label: 'Merged', color: 'var(--purple)' },
	{ value: 'unspecified', label: 'Unspecified', color: 'var(--muted)' }
] as const;
export const outcomeOf = (raw: RawTask) => outcomes.find((item) => item.value === raw.outcome)?.value ?? 'unspecified';
export const inProject = (project: string, parent: string) => project === parent || project.startsWith(`${parent}.`);
const references = (value: unknown): string[] => Array.isArray(value)
	? value.map(String) : typeof value === 'string' ? value.split(',').map((s) => s.trim()).filter(Boolean) : [];

export function text(raw: Record<string, unknown>, key: string): string {
	const value = raw[key];
	return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

function link(label: string, value: string, protocol: string) {
	try {
		const url = new URL(value);
		return url.protocol === protocol ? [{ label, href: url.href }] : [];
	} catch {
		return [];
	}
}

export function normalize(raw: RawTask, now = new Date(), index: ReadonlyMap<string, RawTask> = new Map()) {
	const origins: string[] = [];
	if (raw.logsequuid || raw.logseqid) origins.push('Logseq');
	if (raw.todoistid) origins.push('Todoist');
	if (raw.jiraid) origins.push('Jira');
	if (raw.appleremindersid) origins.push('Apple Reminders');
	if (!origins.length) origins.push('Local');
	const sourceTitle = ['jirasummary', 'logseqtitle', 'todoistcontent', 'applereminderstitle', 'description']
		.map((key) => text(raw, key).trim()).find(Boolean) || 'Untitled task';
	const description = text(raw, 'description').trim();
	const title = description && !description.startsWith('(bw)') ? description : sourceTitle;
	const open = ['pending', 'waiting'].includes(raw.status);
	const hidden = open && (date(raw.wait)?.getTime() ?? 0) > now.getTime();
	const scheduled = open && (date(raw.scheduled)?.getTime() ?? 0) >= now.getTime();
	const blocked = open && references(raw.depends).some((id) => ['pending', 'waiting'].includes(index.get(id)?.status || ''));
	let reminder: { due?: { date_only?: boolean; local_date?: string; value?: string } } = {};
	if (raw.appleremindersmetadata) {
		try { reminder = JSON.parse(String(raw.appleremindersmetadata)) || {}; } catch { /* Keep the original metadata available in attributes. */ }
	}
	return {
		raw,
		uuid: raw.uuid,
		status: raw.status,
		title,
		project: text(raw, 'project'),
		area: text(raw, 'project').split('.')[0],
		page: text(raw, 'logseqpage'),
		context: text(raw, 'logseqcontext'),
		sourceProject: text(raw, 'logseqproject'),
		list: text(raw, 'applereminderslist'),
		waitingFor: text(raw, 'waitingfor'),
		outcome: outcomeOf(raw),
		open, hidden, scheduled, blocked, ready: open && !hidden && !scheduled && !blocked,
		workflow: !open ? raw.status : hidden ? 'Hidden until' : blocked ? 'Blocked' : scheduled ? 'Scheduled' : 'Ready',
		followUp: date(raw.scheduled) ?? date(raw.wait),
		allDayDue: reminder.due?.date_only && date(reminder.due.value)?.getTime() === date(raw.due)?.getTime() ? reminder.due.local_date : undefined,
		sources: origins,
		urgency: Number(raw.urgency) || 0,
		tags: (raw.tags ?? []) as string[],
		annotations: (raw.annotations ?? []) as { entry: string; description: string }[],
		links: [
			...link('Open in Logseq', text(raw, 'logsequri'), 'logseq:'),
			...link('Open in Todoist', text(raw, 'todoisturl'), 'https:'),
			...link('Open in Jira', text(raw, 'jiraurl'), 'https:')
		],
		search: JSON.stringify(Object.values(raw)).toLocaleLowerCase()
	};
}

export function normalizeTasks(tasks: RawTask[], now = new Date()) {
	const index = new Map(tasks.map((task) => [task.uuid, task]));
	return tasks.map((task) => normalize(task, now, index));
}

export function date(value: unknown): Date | null {
	if (typeof value !== 'string' || !value) return null;
	const iso = value.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/, '$1-$2-$3T$4:$5:$6Z');
	const result = new Date(iso);
	return Number.isNaN(result.getTime()) ? null : result;
}

export function dateLabel(value: unknown): string {
	return date(value)?.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) ?? '—';
}

export function shortDateLabel(value: unknown, now = new Date(), precision: 'day' | 'month' = 'day'): string {
	const when = value instanceof Date ? value : date(value);
	return when?.toLocaleDateString(undefined, {
		month: 'short', day: precision === 'day' ? 'numeric' : undefined,
		year: when.getFullYear() === now.getFullYear() ? undefined : 'numeric'
	}) ?? '—';
}

export function matches(task: Task, filters: Record<string, string>) {
	const state = filters.status;
	return (!state || state === 'all' || (state === 'open' ? task.open : state === 'ready' ? task.ready
		: state === 'waiting' ? task.hidden : state === 'scheduled' ? task.scheduled : state === 'blocked' ? task.blocked : task.status === state))
		&& (!filters.source || task.sources.includes(filters.source))
		&& (!filters.area || task.area === filters.area)
		&& (!filters.project || (filters.scope === 'exact' ? task.project === filters.project : inProject(task.project, filters.project)))
		&& (!filters.page || (filters.page === '__missing' ? !task.page : task.page === filters.page))
		&& (!filters.list || task.list === filters.list)
		&& (!filters.tag || task.tags.includes(filters.tag))
		&& (!filters.outcome || (task.status === 'completed' && task.outcome === filters.outcome))
		&& (filters.q || '').toLocaleLowerCase().split(/\s+/).every((term) => task.search.includes(term));
}

export function compare(sort: string) {
	return (a: Task, b: Task) => {
		let result = 0;
		if (sort === 'title') result = a.title.localeCompare(b.title);
		else if (sort === 'modified') result = text(b.raw, 'modified').localeCompare(text(a.raw, 'modified'));
		else if (sort === 'due') result = (date(a.raw.due)?.getTime() ?? Infinity) - (date(b.raw.due)?.getTime() ?? Infinity);
		else if (sort === 'oldest') result = (date(a.raw.entry)?.getTime() ?? Infinity) - (date(b.raw.entry)?.getTime() ?? Infinity);
		else if (sort === 'followup') result = (a.followUp?.getTime() ?? Infinity) - (b.followUp?.getTime() ?? Infinity);
		else result = b.urgency - a.urgency;
		return result || a.title.localeCompare(b.title) || a.uuid.localeCompare(b.uuid);
	};
}

export function relations(task: Task, tasks: Task[]) {
	const result: { kind: string; id: string; task: Task | undefined }[] = [];
	const add = (kind: string, id: string, field = 'uuid') => {
		const found = tasks.find((t) => text(t.raw, field) === id);
		const target = found?.uuid ?? id;
		if (!result.some((r) => r.id === target && r.kind === kind)) result.push({ kind, id: target, task: found });
	};
	for (const id of references(task.raw.depends)) add('Depends on', id);
	if (task.raw.mergedinto) add('Merged into', text(task.raw, 'mergedinto'));
	if (task.raw.todoistparentuuid) add('Parent', text(task.raw, 'todoistparentuuid'));
	else if (task.raw.todoistparentid) add('Parent', text(task.raw, 'todoistparentid'), 'todoistid');
	if (task.raw.jiraparent) add('Parent', text(task.raw, 'jiraparent'), 'jiraid');
	for (const id of references(task.raw.jirasubtasks)) add('Child', id, 'jiraid');
	for (const candidate of tasks) {
		if (candidate.uuid === task.uuid) continue;
		if (candidate.raw.todoistparentuuid === task.uuid
			|| (task.raw.todoistid && candidate.raw.todoistparentid === task.raw.todoistid)
			|| (task.raw.jiraid && candidate.raw.jiraparent === task.raw.jiraid)) add('Child', candidate.uuid);
		if (references(candidate.raw.depends).includes(task.uuid)) add('Blocks', candidate.uuid);
		if (candidate.raw.mergedinto === task.uuid) add('Merged from', candidate.uuid);
	}
	return result;
}
