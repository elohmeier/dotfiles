<script lang="ts">
	import { RadioGroup } from 'bits-ui';
	import { BarChart, Tooltip } from 'layerchart';
	import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
	import ChartColumn from '@lucide/svelte/icons/chart-column';
	import Choice from './choice.svelte';
	import SearchChoice from './search-choice.svelte';
	import DateRange from './date-range.svelte';
	import { activity, customRange, type Grain, type Range } from '#lib/activity.js';
	import { dateLabel, shortDateLabel, outcomes, type Task } from '#lib/tasks.js';

	let { tasks, now, params, pages, onchange, onopen }: {
		tasks: Task[]; now: Date; params: Pick<URLSearchParams, 'get'>; pages: string[];
		onchange: (changes: Record<string, string | null>) => void;
		onopen: (uuid: string) => void;
	} = $props();
	const custom = $derived(customRange(params.get('from'), params.get('to'), now));
	const range = $derived((['30', '90', '365', 'all', 'year', 'last-year', ...(custom ? ['custom'] : [])].includes(params.get('range') || '') ? params.get('range') : '90') as Range);
	const grain = $derived((['day', 'week', 'month'].includes(params.get('grain') || '') ? params.get('grain') : 'week') as Grain);
	const rollup = $derived(params.get('rollup') === 'area' ? 'area' : 'project');
	const series = $derived(outcomes.filter((item) => !params.get('outcome') || item.value === params.get('outcome')).map((item) => ({ key: item.value, value: item.value, label: item.label, color: item.color })));
	const report = $derived(activity(tasks, range, grain, now, custom, { rollup, outcome: params.get('outcome') || '' }));
	const period = $derived(report.buckets.find((bucket) => bucket.key === params.get('period'))
		?? report.buckets.findLast((bucket) => bucket.count > 0) ?? report.buckets.at(-1)!);
	const maxCount = $derived(Math.max(1, ...report.buckets.map((bucket) => bucket.count)));
	const ticks = $derived(report.buckets.filter((_, i) => i % Math.ceil(report.buckets.length / 6) === 0).map((bucket) => bucket.key));
	const projects = $derived(report.projects.slice(0, 6).map(({ project, count }) => ({ key: project, label: project, count })));
	const bounds = $derived(`${report.start.toLocaleDateString(undefined, { dateStyle: 'medium' })} – ${report.to.toLocaleDateString(undefined, { dateStyle: 'medium' })}`);
	const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
	const stats = $derived([
		{ label: 'Closed', value: report.closed.toLocaleString(), note: 'in the selected date range' },
		{ label: 'Per week', value: report.perWeek.toLocaleString(undefined, { maximumFractionDigits: 1 }), note: `average across ${report.days} calendar days` },
		{ label: 'Days with closures', value: report.activeDays.toLocaleString(), note: `of ${report.days} calendar days` },
		{ label: 'Open now', value: report.open.toLocaleString(), note: 'pending and waiting · all dates' }
	]);

	function tickLabel(key: string) {
		const value = new Date(`${key}T12:00:00`);
		return shortDateLabel(value, now, grain === 'month' ? 'month' : 'day');
	}
</script>

<section class="activity" aria-label="Closure activity">
	<div class="activity-heading">
		<div><p class="eyebrow">Your task history</p><h1>Closure activity</h1><p class="activity-subtitle">{bounds} <span>·</span> {params.get('project') || params.get('area') || 'All areas'} <span>·</span> {params.get('source') || 'All sources'}</p></div>
		<div class="activity-controls">
			{#if pages.length}<SearchChoice label="Logseq page" value={params.get('page') || '__all'} options={[{ value: '__all', label: 'All Logseq pages' }, { value: '__missing', label: 'No page metadata' }, ...pages.map((name) => ({ value: name, label: name }))]} onchange={(value) => onchange({ page: value === '__all' ? null : value, period: null })} />{/if}
			<DateRange {range} from={report.start} to={report.to} {now} {onchange} />
		</div>
	</div>
	<div class="activity-stats">
		{#each stats as stat}<article><p>{stat.label}</p><strong>{stat.value}</strong><small>{stat.note}</small></article>{/each}
	</div>
	<div class="chart-card">
		<div class="chart-heading"><div><h2>Closures over time</h2><p>Tasks closed per {grain}. Empty periods are included.</p></div>
			<RadioGroup.Root class="segmented" orientation="horizontal" value={grain} onValueChange={(value) => onchange({ grain: value, period: null })} aria-label="Group closures by">
				{#each ['day', 'week', 'month'] as value}<RadioGroup.Item {value}>{value.charAt(0).toUpperCase() + value.slice(1)}</RadioGroup.Item>{/each}
			</RadioGroup.Root>
		</div>
		<figure class="activity-chart timeline-chart" aria-label={`${report.closed} closed tasks grouped by ${grain}`}>
			<BarChart data={report.buckets} x="key" y="count" yDomain={[0, maxCount]} yNice padding={{ left: 35, right: 12, top: 15, bottom: 30 }}
				{series} seriesLayout="stack"
				onTooltipClick={(_, { data }) => onchange({ period: data.key })}
				props={{ bars: { stroke: 'none', radius: 3, motion: { type: 'tween', duration: 0 } },
					xAxis: { ticks, format: tickLabel, rule: false }, yAxis: { ticks: Math.min(maxCount, 5), format: (value: number) => Number.isInteger(value) ? String(value) : '', rule: false } }}>
				{#snippet tooltip()}<Tooltip.Root variant="none">{#snippet children({ data })}<div class="activity-tooltip"><strong>{data.label}</strong><span>{data.count} closed</span>{#each outcomes as item}{#if data[item.value]}<span class="tooltip-outcome"><i style:background={item.color}></i>{item.label}: {data[item.value]}</span>{/if}{/each}<small>Click to inspect tasks</small></div>{/snippet}</Tooltip.Root>{/snippet}
			</BarChart>
		</figure>
		<div class="outcome-legend" aria-label="Closure outcomes">{#each series as item}<span><i style:background={item.color}></i>{item.label}</span>{/each}</div>
		<div class="chart-footnote"><span>Select a bar or choose a period below to inspect its tasks.</span><span>{timezone} · weeks start Monday · edge periods may be partial</span></div>
	</div>
	<div class="activity-lower">
		<section class="chart-card project-chart-card" aria-label="Closures by area or project">
			<div class="chart-heading"><div><h2>Closed by {rollup}</h2><p>Top six {rollup === 'area' ? 'areas' : 'projects'} in the selected date range.</p></div><Choice label="Aggregate closures by" value={rollup} options={[{ value: 'area', label: 'By area' }, { value: 'project', label: 'By project' }]} onchange={(value) => onchange({ rollup: value === 'project' ? null : value })} /></div>
			{#if projects.length}<figure class="activity-chart project-chart" aria-label="Closure counts for the top groups">
				<BarChart data={projects} orientation="horizontal" x="count" y="key" xDomain={[0, Math.max(1, ...projects.map((p) => p.count))]} xNice
					padding={{ left: 115, right: 18, top: 12, bottom: 28 }} series={[{ key: 'count', label: 'Closed', color: 'var(--purple)' }]}
					props={{ bars: { stroke: 'none', radius: 3, motion: { type: 'tween', duration: 0 } },
						xAxis: { ticks: Math.min(5, Math.max(...projects.map((p) => p.count))), format: (value: number) => Number.isInteger(value) ? String(value) : '', rule: false },
						yAxis: { format: (name: string) => name.length > 17 ? `${name.slice(0, 16)}…` : name, rule: false } }}>
					{#snippet tooltip()}<Tooltip.Root variant="none">{#snippet children({ data })}<div class="activity-tooltip"><strong>{data.label}</strong><span>{data.count} closed</span></div>{/snippet}</Tooltip.Root>{/snippet}
				</BarChart>
			</figure>{:else}<div class="activity-empty"><ChartColumn size={25} /><h3>No closures in this range</h3><p>Try a longer date range or change the source and project filters.</p></div>{/if}
		</section>
		<section class="chart-card period-card" aria-label="Tasks closed in selected period">
			<div class="chart-heading"><div><h2>Inspect a period <span>{period.count}</span></h2><p>Open a task to read its details.</p></div>
				<Choice label="Inspect closure period" value={period.key} options={report.buckets.toReversed().map((bucket) => ({ value: bucket.key, label: `${bucket.label} · ${bucket.count}` }))} onchange={(value) => onchange({ period: value })} />
			</div>
			<div class="period-tasks">
				{#each period.tasks as task (task.uuid)}<button onclick={() => onopen(task.uuid)}><span><strong>{task.title}</strong><small>{task.project || 'No project'} <span>·</span> {dateLabel(task.raw.end)} <span>·</span> {outcomes.find((item) => item.value === task.outcome)?.label}</small></span><ArrowUpRight size={16} /></button>{:else}<div class="activity-empty"><ChartColumn size={25} /><h3>No closures in this period</h3><p>Choose another period to inspect its tasks.</p></div>{/each}
			</div>
		</section>
	</div>
	<p class="activity-method">Closures use Taskwarrior’s <code>end</code> date for tasks currently marked completed. Done, dropped and merged outcomes remain separate; older records without a recognized outcome are unspecified. Deleted tasks are excluded. Imports and bulk updates can create spikes. This snapshot does not retain previous completions of reopened tasks or measure time spent.</p>
	{#if report.missingDates}<p class="activity-method">{report.missingDates} completed {report.missingDates === 1 ? 'task has' : 'tasks have'} no valid closure date and {report.missingDates === 1 ? 'is' : 'are'} excluded from the charts.</p>{/if}
</section>
