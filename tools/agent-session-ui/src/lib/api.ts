export type Session = {
	ref: string;
	id: string;
	agent: 'claude' | 'codex' | 'pi';
	store: string;
	title: string;
	cwd: string;
	cwd_exists: boolean;
	workspace: string;
	branch: string;
	model: string;
	parent: string;
	kind: string;
	updated: number;
	message_count: number;
	first_prompt: string;
	last_reply: string;
	snippet?: string;
	match_line?: number | null;
	resume: string;
};

export type Workspace = {
	key: string;
	name: string;
	exists: boolean;
	count: number;
	updated: number;
	branches: string[];
	cwds: { cwd: string; count: number; updated: number }[];
	latest: Session;
};

export type Block =
	| { type: 'text' | 'summary'; text: string }
	| { type: 'tool'; name: string; input: string; output?: string; error?: boolean }
	| { type: 'image'; mimeType: string };

export type Item = {
	id: string;
	role: 'user' | 'assistant';
	timestamp: string;
	blocks: Block[];
};

export type Detail = { session: Session; focus: string | null; messages: Item[] };

export async function get<T>(path: string, params: Record<string, string | null | undefined> = {}) {
	const query = new URLSearchParams(
		Object.entries(params).filter((entry): entry is [string, string] => !!entry[1])
	);
	const response = await fetch(`/api/${path}?${query}`);
	if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
	return (await response.json()) as T;
}

export function ago(seconds: number) {
	const delta = Date.now() / 1000 - seconds;
	const units: [number, string][] = [
		[31536000, 'y'],
		[2592000, 'mo'],
		[604800, 'w'],
		[86400, 'd'],
		[3600, 'h'],
		[60, 'm']
	];
	const [size, unit] = units.find(([size]) => delta >= size) ?? [1, 's'];
	return delta < 60 ? 'now' : `${Math.floor(delta / size)}${unit}`;
}

export function day(seconds: number) {
	const date = new Date(seconds * 1000);
	const today = new Date();
	const days = Math.round(
		(new Date(today.toDateString()).getTime() - new Date(date.toDateString()).getTime()) / 864e5
	);
	if (days === 0) return 'Today';
	if (days === 1) return 'Yesterday';
	return date.toLocaleDateString(undefined, {
		weekday: days < 7 ? 'long' : undefined,
		day: 'numeric',
		month: 'short',
		year: days > 300 ? 'numeric' : undefined
	});
}

export const home = (path: string) => path.replace(/^\/(Users|home)\/[^/]+/, '~');
