import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { compare, date, matches, normalize, normalizeTasks, relations, type RawTask } from './tasks.ts';

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

test('workflow distinguishes hidden, scheduled and blocked tasks from ready actions', () => {
	const now = new Date('2026-11-12T12:00:00Z');
	const records = [
		raw({ uuid: 'hidden', wait: '20261113T120000Z', tags: ['delegated'], waitingfor: 'Fixture Person' }),
		raw({ uuid: 'scheduled', scheduled: '20261112T120000Z' }),
		raw({ uuid: 'blocked', depends: ['hidden'] }),
		raw({ uuid: 'done', status: 'completed', wait: '20261113T120000Z' }),
		raw({ uuid: 'ready', wait: '20261112T120000Z', depends: ['done', 'missing'] })
	];
	const tasks = normalizeTasks(records, now);
	const ids = (status: string) => tasks.filter((task) => matches(task, { status })).map((task) => task.uuid);
	assert.deepEqual(ids('waiting'), ['hidden']);
	assert.deepEqual(ids('scheduled'), ['scheduled']);
	assert.deepEqual(ids('blocked'), ['blocked']);
	assert.deepEqual(ids('ready'), ['ready']);
	assert.deepEqual(ids('open'), ['hidden', 'scheduled', 'blocked', 'ready']);
	assert.equal(tasks[0].status, 'pending');
	assert.equal(tasks[0].waitingFor, 'Fixture Person');
	assert.equal(normalizeTasks(records, new Date('2026-11-14T00:00:00Z'))[0].ready, true);
});

test('Reminders retain provenance and all-day dates without inventing source links', () => {
	const record = raw({ appleremindersid: 'reminder-1', applereminderstitle: 'Original title',
		applereminderslist: 'Someday', project: 'Inbox', due: '20261112T225959Z',
		appleremindersurl: 'facetime:fixture', appleremindersmetadata: JSON.stringify({ due: { date_only: true, local_date: '2026-11-12', value: '2026-11-12T22:59:59Z' } }) });
	const task = normalize(record);
	assert.deepEqual(task.sources, ['Apple Reminders']);
	assert.equal(task.list, 'Someday');
	assert.equal(task.project, 'Inbox');
	assert.equal(task.allDayDue, '2026-11-12');
	assert.deepEqual(task.links, []);
	assert.equal(normalize({ ...record, due: '20261113T120000Z' }).allDayDue, undefined);
	assert.equal(normalize({ ...record, appleremindersmetadata: 'invalid' }).allDayDue, undefined);
});

test('project subtrees respect dot boundaries and support exact area and workflow facets', () => {
	const task = normalize(raw({ project: 'Work.Platform.API', tags: ['verify'], outcome: 'merged', status: 'completed', applereminderslist: 'Inbox' }));
	assert(matches(task, { project: 'Work' }));
	assert(matches(task, { project: 'Work.Platform' }));
	assert(!matches(task, { project: 'Work', scope: 'exact' }));
	assert(!matches(task, { project: 'Wor' }));
	assert(matches(task, { area: 'Work', tag: 'verify', outcome: 'merged', list: 'Inbox' }));
	assert(!matches(task, { area: 'Work.Platform' }));
	assert(!matches(task, { tag: 'next' }));
	assert(!matches(task, { outcome: 'done' }));
	assert(!matches(normalize(raw({ outcome: 'done' })), { outcome: 'done' }));
});

test('merge links resolve in both directions without altering task identities', () => {
	const target = normalize(raw({ uuid: 'survivor' }));
	const duplicate = normalize(raw({ uuid: 'duplicate', status: 'completed', outcome: 'merged', mergedinto: 'survivor' }));
	assert.equal(relations(duplicate, [duplicate, target]).find((link) => link.kind === 'Merged into')?.task?.uuid, 'survivor');
	assert.equal(relations(target, [duplicate, target]).find((link) => link.kind === 'Merged from')?.task?.uuid, 'duplicate');
	assert.equal(relations(duplicate, [duplicate])[0].id, 'survivor');
	assert.equal(relations(duplicate, [duplicate])[0].task, undefined);
});

test('review and follow-up sorts put undated tasks last', () => {
	const tasks = normalizeTasks([
		raw({ uuid: 'later', entry: '20261101T120000Z', scheduled: '20261201T120000Z' }),
		raw({ uuid: 'earlier', entry: '20260101T120000Z', wait: '20261120T120000Z' }),
		raw({ uuid: 'undated' })
	]);
	assert.deepEqual([...tasks].sort(compare('oldest')).map((task) => task.uuid), ['earlier', 'later', 'undated']);
	assert.deepEqual([...tasks].sort(compare('followup')).map((task) => task.uuid), ['earlier', 'later', 'undated']);
});
