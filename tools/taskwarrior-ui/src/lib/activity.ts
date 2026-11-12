import { date, type Task } from './tasks.ts';

export type Range = '30' | '90' | '365' | 'all';
export type Grain = 'day' | 'week' | 'month';

export const dayKey = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
const midnight = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate());
const calendarDay = (value: Date) => Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()) / 86_400_000;

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

export function activity(tasks: Task[], range: Range, grain: Grain, now: Date) {
	const completed = tasks.filter((task) => task.status === 'completed');
	const dated = completed.flatMap((task) => {
		const when = date(task.raw.end);
		return when ? [{ task, when }] : [];
	});
	const occurred = dated.filter(({ when }) => when <= now);
	const today = midnight(now);
	const end = next(today, 'day');
	const start = new Date(today);
	if (range === 'all' && occurred.length) start.setTime(Math.min(...occurred.map(({ when }) => midnight(when).getTime())));
	else start.setDate(start.getDate() - (range === 'all' ? 30 : Number(range)) + 1);
	const events = occurred.filter(({ when }) => when >= start);
	const buckets = [];
	for (let cursor = startOf(start, grain); cursor < end; cursor = next(cursor, grain)) {
		const until = next(cursor, grain);
		const from = new Date(Math.max(cursor.getTime(), start.getTime()));
		const to = new Date(Math.min(until.getTime(), end.getTime()) - 1);
		const label = grain === 'day' ? from.toLocaleDateString(undefined, { dateStyle: 'medium' })
			: `${from.toLocaleDateString(undefined, { dateStyle: 'medium' })} – ${to.toLocaleDateString(undefined, { dateStyle: 'medium' })}`;
		buckets.push({ key: dayKey(cursor), date: new Date(cursor), label, count: 0, tasks: [] as Task[] });
	}
	const byKey = new Map(buckets.map((bucket) => [bucket.key, bucket]));
	for (const { task, when } of events) {
		const bucket = byKey.get(dayKey(startOf(when, grain)))!;
		bucket.count += 1;
		bucket.tasks.push(task);
	}
	for (const bucket of buckets) bucket.tasks.sort((a, b) => String(b.raw.end).localeCompare(String(a.raw.end)) || a.title.localeCompare(b.title));
	const projects = new Map<string, number>();
	for (const { task } of events) projects.set(task.project || 'No project', (projects.get(task.project || 'No project') ?? 0) + 1);
	const days = calendarDay(end) - calendarDay(start);
	return {
		start, end, days, buckets,
		completed: events.length,
		perWeek: events.length / days * 7,
		activeDays: new Set(events.map(({ when }) => dayKey(when))).size,
		open: tasks.filter((task) => ['pending', 'waiting'].includes(task.status)).length,
		missingDates: completed.length - dated.length,
		projects: [...projects].map(([project, count]) => ({ project, count })).sort((a, b) => b.count - a.count || a.project.localeCompare(b.project))
	};
}
