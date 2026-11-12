<script lang="ts">
	import { RadioGroup } from 'bits-ui';
	import { BarChart, Tooltip } from 'layerchart';
	import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
	import ChartColumn from '@lucide/svelte/icons/chart-column';
	import Choice from './choice.svelte';
	import { activity, type Grain, type Range } from '#lib/activity.js';
	import { dateLabel, shortDateLabel, type Task } from '#lib/tasks.js';

	let { tasks, now, params, pages, onchange, onopen }: {
		tasks: Task[]; now: Date; params: Pick<URLSearchParams, 'get'>; pages: string[];
		onchange: (changes: Record<string, string | null>) => void;
		onopen: (uuid: string) => void;
	} = $props();
	const range = $derived((['30', '90', '365', 'all'].includes(params.get('range') || '') ? params.get('range') : '90') as Range);
	const grain = $derived((['day', 'week', 'month'].includes(params.get('grain') || '') ? params.get('grain') : 'week') as Grain);
	const report = $derived(activity(tasks, range, grain, now));
	const period = $derived(report.buckets.find((bucket) => bucket.key === params.get('period'))
		?? report.buckets.findLast((bucket) => bucket.count > 0) ?? report.buckets.at(-1)!);
	const maxCount = $derived(Math.max(1, ...report.buckets.map((bucket) => bucket.count)));
	const ticks = $derived(report.buckets.filter((_, i) => i % Math.ceil(report.buckets.length / 6) === 0).map((bucket) => bucket.key));
	const projects = $derived(report.projects.slice(0, 6).map(({ project, count }) => ({ key: project, label: project, count })));
	const bounds = $derived(`${report.start.toLocaleDateString(undefined, { dateStyle: 'medium' })} – ${now.toLocaleDateString(undefined, { dateStyle: 'medium' })}`);
	const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
	const stats = $derived([
		{ label: 'Completed', value: report.completed.toLocaleString(), note: 'in the selected date range' },
		{ label: 'Per week', value: report.perWeek.toLocaleString(undefined, { maximumFractionDigits: 1 }), note: `average across ${report.days} calendar days` },
		{ label: 'Days with completions', value: report.activeDays.toLocaleString(), note: `of ${report.days} calendar days` },
		{ label: 'Open now', value: report.open.toLocaleString(), note: 'pending and waiting · all dates' }
	]);

	function tickLabel(key: string) {
		const value = new Date(`${key}T12:00:00`);
		return shortDateLabel(value, now, grain === 'month' ? 'month' : 'day');
	}
</script>

<section class="activity" aria-label="Completion activity">
	<div class="activity-heading">
		<div><p class="eyebrow">Your task history</p><h1>Completion activity</h1><p class="activity-subtitle">{bounds} <span>·</span> {params.get('project') || 'All projects'} <span>·</span> {params.get('source') || 'All sources'}</p></div>
		<div class="activity-controls">
			{#if pages.length}<Choice label="Filter by Logseq page" value={params.get('page') || 'all'} options={[{ value: 'all', label: 'All Logseq pages' }, { value: '__missing', label: 'No page metadata' }, ...pages.map((name) => ({ value: name, label: name }))]} onchange={(value) => onchange({ page: value === 'all' ? null : value, period: null })} />{/if}
			<Choice label="Date range" value={range} options={[{ value: '30', label: 'Last 30 days' }, { value: '90', label: 'Last 90 days' }, { value: '365', label: 'Last 365 days' }, { value: 'all', label: 'All time' }]} onchange={(value) => onchange({ range: value, period: null })} />
		</div>
	</div>
	<div class="activity-stats">
		{#each stats as stat}<article><p>{stat.label}</p><strong>{stat.value}</strong><small>{stat.note}</small></article>{/each}
	</div>
	<div class="chart-card">
		<div class="chart-heading"><div><h2>Completed over time</h2><p>Tasks completed per {grain}. Empty periods are included.</p></div>
			<RadioGroup.Root class="segmented" orientation="horizontal" value={grain} onValueChange={(value) => onchange({ grain: value, period: null })} aria-label="Group completions by">
				{#each ['day', 'week', 'month'] as value}<RadioGroup.Item {value}>{value.charAt(0).toUpperCase() + value.slice(1)}</RadioGroup.Item>{/each}
			</RadioGroup.Root>
		</div>
		<figure class="activity-chart timeline-chart" aria-label={`${report.completed} completed tasks grouped by ${grain}`}>
			<BarChart data={report.buckets} x="key" y="count" yDomain={[0, maxCount]} yNice padding={{ left: 35, right: 12, top: 15, bottom: 30 }}
				series={[{ key: 'count', label: 'Completed', color: 'var(--accent)' }]}
				onTooltipClick={(_, { data }) => onchange({ period: data.key })}
				props={{ bars: { stroke: 'none', radius: 3, motion: { type: 'tween', duration: 0 } },
					xAxis: { ticks, format: tickLabel, rule: false }, yAxis: { ticks: Math.min(maxCount, 5), format: (value: number) => Number.isInteger(value) ? String(value) : '', rule: false } }}>
				{#snippet tooltip()}<Tooltip.Root variant="none">{#snippet children({ data })}<div class="activity-tooltip"><strong>{data.label}</strong><span>{data.count} completed</span><small>Click to inspect tasks</small></div>{/snippet}</Tooltip.Root>{/snippet}
			</BarChart>
		</figure>
		<div class="chart-footnote"><span>Select a bar or choose a period below to inspect its tasks.</span><span>{timezone} · weeks start Monday · edge periods may be partial</span></div>
	</div>
	<div class="activity-lower">
		<section class="chart-card project-chart-card" aria-label="Completed by project">
			<div class="chart-heading"><div><h2>Completed by project</h2><p>Top six projects in the selected date range.</p></div></div>
			{#if projects.length}<figure class="activity-chart project-chart" aria-label="Completion counts for the top projects">
				<BarChart data={projects} orientation="horizontal" x="count" y="key" xDomain={[0, Math.max(1, ...projects.map((p) => p.count))]} xNice
					padding={{ left: 115, right: 18, top: 12, bottom: 28 }} series={[{ key: 'count', label: 'Completed', color: 'var(--purple)' }]}
					props={{ bars: { stroke: 'none', radius: 3, motion: { type: 'tween', duration: 0 } },
						xAxis: { ticks: Math.min(5, Math.max(...projects.map((p) => p.count))), format: (value: number) => Number.isInteger(value) ? String(value) : '', rule: false },
						yAxis: { format: (name: string) => name.length > 17 ? `${name.slice(0, 16)}…` : name, rule: false } }}>
					{#snippet tooltip()}<Tooltip.Root variant="none">{#snippet children({ data })}<div class="activity-tooltip"><strong>{data.label}</strong><span>{data.count} completed</span></div>{/snippet}</Tooltip.Root>{/snippet}
				</BarChart>
			</figure>{:else}<div class="activity-empty"><ChartColumn size={25} /><h3>No completions in this range</h3><p>Try a longer date range or change the source and project filters.</p></div>{/if}
		</section>
		<section class="chart-card period-card" aria-label="Tasks completed in selected period">
			<div class="chart-heading"><div><h2>Inspect a period <span>{period.count}</span></h2><p>Open a task to read its details.</p></div>
				<Choice label="Inspect completion period" value={period.key} options={report.buckets.toReversed().map((bucket) => ({ value: bucket.key, label: `${bucket.label} · ${bucket.count}` }))} onchange={(value) => onchange({ period: value })} />
			</div>
			<div class="period-tasks">
				{#each period.tasks as task (task.uuid)}<button onclick={() => onopen(task.uuid)}><span><strong>{task.title}</strong><small>{task.project || 'No project'} <span>·</span> {dateLabel(task.raw.end)}</small></span><ArrowUpRight size={16} /></button>{:else}<div class="activity-empty"><ChartColumn size={25} /><h3>No completions in this period</h3><p>Choose another period to inspect its tasks.</p></div>{/each}
			</div>
		</section>
	</div>
	<p class="activity-method">Counts use Taskwarrior’s completion date (<code>end</code>) for tasks currently marked completed. Deleted tasks are excluded. Imports and bulk updates can create spikes. This snapshot does not retain previous completions of reopened tasks or measure time spent.</p>
	{#if report.missingDates}<p class="activity-method">{report.missingDates} completed {report.missingDates === 1 ? 'task has' : 'tasks have'} no valid completion date and {report.missingDates === 1 ? 'is' : 'are'} excluded from the charts.</p>{/if}
</section>
