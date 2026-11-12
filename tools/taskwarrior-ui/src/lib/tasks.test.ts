import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { compare, date, matches, normalize, relations, type RawTask } from './tasks.ts';

const raw = (fields: Partial<RawTask> = {}): RawTask => ({
	uuid: 'task-1', status: 'pending', description: '(bw) truncated…', ...fields
});

test('mixed sources retain full titles, both links, and independent statuses', () => {
	const task = normalize(raw({ logsequuid: 'block-1', logseqtitle: 'Vollständiger Titel 🏡',
		logseqstate: 'TODO', status: 'completed', logsequri: 'logseq://graph/Documents?block-id=block-1',
		todoistid: '42', todoistcontent: 'Other source title', todoisturl: 'https://app.todoist.com/app/task/42' }));
	assert.equal(task.title, 'Vollständiger Titel 🏡');
	assert.deepEqual(task.sources, ['Logseq', 'Todoist']);
	assert.equal(task.links.length, 2);
	assert.equal(task.status, 'completed');
	assert.equal(task.raw.logseqstate, 'TODO');
	assert(matches(task, { status: 'completed', source: 'Todoist', q: 'vollständiger 42' }));
	assert(!matches(task, { status: 'pending', q: '' }));
});

test('unsafe source links remain text and missing metadata can be filtered', () => {
	const task = normalize(raw({ jiraid: 'KEY-1', jirasummary: '<script>alert(1)</script>', jiraurl: 'javascript:alert(1)' }));
	assert.deepEqual(task.links, []);
	assert.equal(task.title, '<script>alert(1)</script>');
	assert(matches(task, { q: '', page: '__missing' }));
	assert(!matches(task, { q: '', page: 'Some page' }));
});

test('a CLI description change takes precedence over imported titles', () => {
	const task = normalize(raw({ description: 'My revised title', logsequuid: 'block-1', logseqtitle: 'Imported title' }));
	assert.equal(task.title, 'My revised title');
	assert.equal(task.raw.logseqtitle, 'Imported title');
});

test('Taskwarrior UTC dates parse and undated tasks sort last', () => {
	assert.equal(date('20261112T120000Z')?.toISOString(), '2026-11-12T12:00:00.000Z');
	assert.equal(date('invalid'), null);
	const dated = normalize(raw({ uuid: 'dated', due: '20261112T120000Z' }));
	const undated = normalize(raw());
	assert.deepEqual([undated, dated].sort(compare('due')).map((t) => t.uuid), ['dated', 'task-1']);
});

test('relationships resolve UUIDs and source IDs without merging records', () => {
	const parent = normalize(raw({ todoistid: '10' }));
	const child = normalize(raw({ uuid: 'child', todoistid: '11', todoistparentid: '10', todoistparentuuid: 'task-1', depends: ['missing'] }));
	assert.equal(relations(parent, [parent, child]).length, 1);
	const links = relations(child, [parent, child]);
	assert.equal(links.find((r) => r.kind === 'Parent')?.task?.uuid, parent.uuid);
	assert.equal(links.find((r) => r.kind === 'Depends on')?.task, undefined);
});
