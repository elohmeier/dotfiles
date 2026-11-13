import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { activity, customRange } from './activity.ts';
import { matches, normalize, type RawTask } from './tasks.ts';

process.env.TZ = 'Europe/Berlin';
const now = new Date(2026, 10, 12, 18);
let id = 0;
const task = (fields: Partial<RawTask> = {}) => normalize({ uuid: String(++id), description: 'Fixture', status: 'completed', ...fields });

test('completion counts exclude deleted, reopened, future and undated records; zero days remain visible', () => {
	const report = activity([
		task({ end: '20261112T120000Z' }), task({ status: 'deleted', end: '20261112T120000Z' }),
		task({ status: 'pending', end: '20261112T120000Z' }), task({ end: '20261113T120000Z' }),
		task({ end: 'invalid' }), task()
	], '30', 'day', now);
	assert.equal(report.closed, 1);
	assert.equal(report.open, 1);
	assert.equal(report.missingDates, 2);
	assert.equal(report.buckets.length, 30);
	assert.equal(report.buckets.at(-1)?.count, 1);
	assert.equal(report.buckets.filter((bucket) => bucket.count === 0).length, 29);
	assert.equal(report.buckets.reduce((sum, bucket) => sum + bucket.count, 0), report.closed);
});

test('day buckets use the browser timezone, including timestamps near midnight', () => {
	const report = activity([task({ end: '20261111T233000Z' }), task({ end: '20261111T220000Z' })], '30', 'day', now);
	assert.equal(report.buckets.at(-1)?.key, '2026-11-12');
	assert.equal(report.buckets.at(-1)?.count, 1);
	assert.equal(report.buckets.at(-2)?.count, 1);
});

test('weeks begin on Monday across year boundaries and months include zero periods', () => {
	const tasks = [task({ end: '20251231T120000Z' }), task({ end: '20260101T120000Z' }), task({ end: '20260302T120000Z' })];
	const weekly = activity(tasks, 'all', 'week', new Date(2026, 2, 5));
	assert.equal(weekly.buckets[0].key, '2025-12-29');
	assert.equal(weekly.buckets[0].count, 2);
	const monthly = activity(tasks, 'all', 'month', new Date(2026, 2, 5));
	assert.deepEqual(monthly.buckets.map((bucket) => bucket.count), [1, 1, 0, 1]);
});

test('calendar-day averages remain correct across daylight saving changes', () => {
	const report = activity([task({ end: '20260329T120000Z' })], '30', 'day', new Date(2026, 2, 30, 18));
	assert.equal(report.days, 30);
	assert.equal(report.buckets.length, 30);
	assert.equal(report.perWeek, 7 / 30);
});

test('shared source metadata is counted once and project/source scope applies to all statistics', () => {
	const mixed = task({ project: 'Work', logsequuid: 'block', todoistid: '42', end: '20261112T120000Z' });
	const tasks = [mixed, task({ project: 'Home', end: '20261112T120000Z' }), task({ status: 'waiting', project: 'Work', todoistid: '43' })];
	const scoped = tasks.filter((t) => matches(t, { q: '', project: 'Work', source: 'Todoist', status: 'all' }));
	const report = activity(scoped, '30', 'week', now);
	assert.equal(report.closed, 1);
	assert.equal(report.open, 1);
	assert.deepEqual(report.projects, [{ project: 'Work', count: 1 }]);
	assert.equal(report.activeDays, 1);
});

test('empty history produces a useful zero-filled range', () => {
	const report = activity([], 'all', 'day', now);
	assert.equal(report.buckets.length, 30);
	assert.equal(report.closed, 0);
	assert.equal(report.perWeek, 0);
});

test('custom ranges include the entire final local day and exclude later completions', () => {
	const custom = customRange('2026-03-28', '2026-03-29', now)!;
	const report = activity([
		task({ end: '20260327T225959Z' }), task({ end: '20260327T230000Z' }),
		task({ end: '20260329T215959Z' }), task({ end: '20260329T220000Z' })
	], 'custom', 'day', now, custom);
	assert.equal(report.closed, 2);
	assert.equal(report.days, 2);
	assert.deepEqual(report.buckets.map((bucket) => bucket.count), [1, 1]);
	assert.equal(report.perWeek, 7);
});

test('calendar-year presets respect local year boundaries and leap years', () => {
	const tasks = [task({ end: '20241231T225959Z' }), task({ end: '20241231T230000Z' }), task({ end: '20251231T230000Z' })];
	const lastYear = activity(tasks, 'last-year', 'month', now);
	assert.equal(lastYear.closed, 1);
	assert.equal(lastYear.days, 365);
	assert.equal(lastYear.buckets.length, 12);
	assert.equal(activity(tasks, 'year', 'month', now).closed, 1);
	assert.equal(activity([], 'last-year', 'month', new Date(2025, 1, 1)).days, 366);
});

test('custom range URLs reject impossible, reversed and future dates', () => {
	assert.equal(customRange('2026-02-30', '2026-03-02', now), undefined);
	assert.equal(customRange('2026-11-12', '2026-11-11', now), undefined);
	assert.equal(customRange('2026-11-12', '2026-11-13', now), undefined);
	assert.equal(customRange('invalid', '2026-11-12', now), undefined);
	assert.equal(customRange(null, null, now), undefined);
	assert(customRange('2026-11-12', '2026-11-12', now));
});

test('closure stacks preserve done, dropped, merged and unspecified outcomes', () => {
	const tasks = ['done', 'dropped', 'merged', '', 'unknown'].map((outcome) => task({ outcome, end: '20261112T120000Z' }));
	const report = activity(tasks, '30', 'day', now);
	assert.equal(report.closed, 5);
	const bucket = report.buckets.at(-1)!;
	assert.deepEqual([bucket.done, bucket.dropped, bucket.merged, bucket.unspecified], [1, 1, 1, 2]);
	assert.equal(bucket.done + bucket.dropped + bucket.merged + bucket.unspecified, bucket.count);
});

test('area rollups combine subprojects and outcome filtering keeps open scope intact', () => {
	const tasks = [task({ project: 'Work.One', outcome: 'done', end: '20261112T120000Z' }),
		task({ project: 'Work.Two', outcome: 'dropped', end: '20261112T120000Z' }),
		task({ project: 'Home', outcome: 'merged', end: '20261112T120000Z' }), task({ project: 'Work.One', status: 'pending' })];
	assert.deepEqual(activity(tasks, '30', 'week', now, undefined, { rollup: 'area' }).projects, [{ project: 'Work', count: 2 }, { project: 'Home', count: 1 }]);
	const report = activity(tasks, '30', 'week', now, undefined, { rollup: 'area', outcome: 'done' });
	assert.equal(report.closed, 1);
	assert.equal(report.open, 1);
	assert.deepEqual(report.projects, [{ project: 'Work', count: 1 }]);
	const history = [task({ end: '20260101T120000Z', outcome: 'done' }), task({ end: '20261112T120000Z', outcome: 'merged' })];
	assert.equal(activity(history, 'all', 'month', now).start.getTime(), activity(history, 'all', 'month', now, undefined, { outcome: 'merged' }).start.getTime());
});
