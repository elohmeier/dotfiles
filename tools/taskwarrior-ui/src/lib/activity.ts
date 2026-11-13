import { date, type Task } from './tasks.ts';

export type Range = '30' | '90' | '365' | 'all' | 'year' | 'last-year' | 'custom';
export type Grain = 'day' | 'week' | 'month';
export type CustomRange = { from: Date; to: Date };

export const dayKey = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
const midnight = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate());
const calendarDay = (value: Date) => Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()) / 86_400_000;

export function customRange(from: string | null, to: string | null, now: Date): CustomRange | undefined {
	if (!from || !to || !/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return;
	const start = new Date(`${from}T00:00:00`);
	const end = new Date(`${to}T00:00:00`);
	if (dayKey(start) === from && dayKey(end) === to && start <= end && end <= midnight(now)) return { from: start, to: end };
}

function startOf(value: Date, grain: Grain) {
	const result = midnight(value);
	if (grain === 'week') result.setDate(result.getDate() - (result.getDay() + 6) % 7);
	if (grain === 'month') result.setDate(1);
	return result;
}

function next(value: Date, grain: Grain) {
	const result = new Date(value);
	if (grain === 'month') result.setMonth(result.getMonth() + 1);
	else result.setDate(result.getDate() + (grain === 'week' ? 7 : 1));
	return result;
}

export function activity(tasks: Task[], range: Range, grain: Grain, now: Date, custom?: CustomRange,
	{ rollup = 'project', outcome = '' }: { rollup?: string; outcome?: string } = {}) {
	const completed = tasks.filter((task) => task.status === 'completed');
	const dated = completed.flatMap((task) => {
		const when = date(task.raw.end);
		return when ? [{ task, when }] : [];
	});
	const occurred = dated.filter(({ when }) => when <= now);
	const today = midnight(now);
	let end = next(today, 'day');
	const start = new Date(today);
	if (range === 'year') start.setMonth(0, 1);
	else if (range === 'last-year') { start.setFullYear(today.getFullYear() - 1, 0, 1); end = new Date(today.getFullYear(), 0, 1); }
	else if (range === 'custom' && custom) { start.setTime(custom.from.getTime()); end = next(custom.to, 'day'); }
	else if (range === 'all' && occurred.length) start.setTime(Math.min(...occurred.map(({ when }) => midnight(when).getTime())));
	else start.setDate(start.getDate() - (range === 'all' ? 30 : range === 'custom' ? 90 : Number(range)) + 1);
	const events = occurred.filter(({ task, when }) => when >= start && when < end && (!outcome || task.outcome === outcome));
	const buckets = [];
	for (let cursor = startOf(start, grain); cursor < end; cursor = next(cursor, grain)) {
		const until = next(cursor, grain);
		const from = new Date(Math.max(cursor.getTime(), start.getTime()));
		const to = new Date(Math.min(until.getTime(), end.getTime()) - 1);
		const label = grain === 'day' ? from.toLocaleDateString(undefined, { dateStyle: 'medium' })
			: `${from.toLocaleDateString(undefined, { dateStyle: 'medium' })} – ${to.toLocaleDateString(undefined, { dateStyle: 'medium' })}`;
		buckets.push({ key: dayKey(cursor), date: new Date(cursor), label, count: 0, done: 0, dropped: 0, merged: 0, unspecified: 0, tasks: [] as Task[] });
	}
	const byKey = new Map(buckets.map((bucket) => [bucket.key, bucket]));
	for (const { task, when } of events) {
		const bucket = byKey.get(dayKey(startOf(when, grain)))!;
		bucket.count += 1;
		bucket[task.outcome] += 1;
		bucket.tasks.push(task);
	}
	for (const bucket of buckets) bucket.tasks.sort((a, b) => String(b.raw.end).localeCompare(String(a.raw.end)) || a.title.localeCompare(b.title));
	const projects = new Map<string, number>();
	for (const { task } of events) {
		const name = (rollup === 'area' ? task.area : task.project) || 'No project';
		projects.set(name, (projects.get(name) ?? 0) + 1);
	}
	const days = calendarDay(end) - calendarDay(start);
	return {
		start, end, to: new Date(end.getTime() - 1), days, buckets,
		closed: events.length,
		perWeek: events.length / days * 7,
		activeDays: new Set(events.map(({ when }) => dayKey(when))).size,
		open: tasks.filter((task) => task.open).length,
		missingDates: completed.filter((task) => (!outcome || task.outcome === outcome) && !date(task.raw.end)).length,
		projects: [...projects].map(([project, count]) => ({ project, count })).sort((a, b) => b.count - a.count || a.project.localeCompare(b.project))
	};
}
