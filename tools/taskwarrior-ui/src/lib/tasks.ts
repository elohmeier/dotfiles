export type RawTask = Record<string, unknown> & {
	uuid: string;
	status: string;
	description: string;
};

export type Snapshot = { tasks: RawTask[]; exportedAt: string | null; error: string };
export type Task = ReturnType<typeof normalize>;
export const sources = ['Logseq', 'Todoist', 'Jira', 'Local'];

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

export function normalize(raw: RawTask) {
	const origins: string[] = [];
	if (raw.logsequuid || raw.logseqid) origins.push('Logseq');
	if (raw.todoistid) origins.push('Todoist');
	if (raw.jiraid) origins.push('Jira');
	if (!origins.length) origins.push('Local');
	const sourceTitle = ['jirasummary', 'logseqtitle', 'todoistcontent', 'description']
		.map((key) => text(raw, key).trim()).find(Boolean) || 'Untitled task';
	const description = text(raw, 'description').trim();
	const title = description && !description.startsWith('(bw)') ? description : sourceTitle;
	return {
		raw,
		uuid: raw.uuid,
		status: raw.status,
		title,
		project: text(raw, 'project'),
		page: text(raw, 'logseqpage'),
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

export function date(value: unknown): Date | null {
	if (typeof value !== 'string' || !value) return null;
	const iso = value.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/, '$1-$2-$3T$4:$5:$6Z');
	const result = new Date(iso);
	return Number.isNaN(result.getTime()) ? null : result;
}

export function dateLabel(value: unknown): string {
	return date(value)?.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) ?? '—';
}

export function matches(task: Task, filters: Record<string, string>) {
	return (!filters.status || filters.status === 'all' || task.status === filters.status)
		&& (!filters.source || task.sources.includes(filters.source))
		&& (!filters.project || task.project === filters.project)
		&& (!filters.page || (filters.page === '__missing' ? !task.page : task.page === filters.page))
		&& filters.q.toLocaleLowerCase().split(/\s+/).every((term) => task.search.includes(term));
}

export function compare(sort: string) {
	return (a: Task, b: Task) => {
		let result = 0;
		if (sort === 'title') result = a.title.localeCompare(b.title);
		else if (sort === 'modified') result = text(b.raw, 'modified').localeCompare(text(a.raw, 'modified'));
		else if (sort === 'due') result = (date(a.raw.due)?.getTime() ?? Infinity) - (date(b.raw.due)?.getTime() ?? Infinity);
		else result = b.urgency - a.urgency;
		return result || a.title.localeCompare(b.title) || a.uuid.localeCompare(b.uuid);
	};
}

const references = (value: unknown): string[] => Array.isArray(value)
	? value.map(String) : typeof value === 'string' ? value.split(',').map((s) => s.trim()).filter(Boolean) : [];

export function relations(task: Task, tasks: Task[]) {
	const result: { kind: string; id: string; task: Task | undefined }[] = [];
	const add = (kind: string, id: string, field = 'uuid') => {
		const found = tasks.find((t) => text(t.raw, field) === id);
		const target = found?.uuid ?? id;
		if (!result.some((r) => r.id === target && r.kind === kind)) result.push({ kind, id: target, task: found });
	};
	for (const id of references(task.raw.depends)) add('Depends on', id);
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
	}
	return result;
}
