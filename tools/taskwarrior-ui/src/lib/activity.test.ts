import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { activity } from './activity.ts';
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
	assert.equal(report.completed, 1);
	assert.equal(report.open, 1);
	assert.equal(report.missingDates, 2);
	assert.equal(report.buckets.length, 30);
	assert.equal(report.buckets.at(-1)?.count, 1);
	assert.equal(report.buckets.filter((bucket) => bucket.count === 0).length, 29);
	assert.equal(report.buckets.reduce((sum, bucket) => sum + bucket.count, 0), report.completed);
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
	assert.equal(report.completed, 1);
	assert.equal(report.open, 1);
	assert.deepEqual(report.projects, [{ project: 'Work', count: 1 }]);
	assert.equal(report.activeDays, 1);
});

test('empty history produces a useful zero-filled range', () => {
	const report = activity([], 'all', 'day', now);
	assert.equal(report.buckets.length, 30);
	assert.equal(report.completed, 0);
	assert.equal(report.perWeek, 0);
});
