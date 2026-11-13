<script lang="ts">
	import { Popover, RangeCalendar, type DateRange } from 'bits-ui';
	import { parseDate, getLocalTimeZone, type DateValue } from '@internationalized/date';
	import { MediaQuery } from 'svelte/reactivity';
	import CalendarDays from '@lucide/svelte/icons/calendar-days';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import { dayKey, customRange, type Range } from '#lib/activity.js';
	let { range, from, to, now, onchange }: {
		range: Range; from: Date; to: Date; now: Date;
		onchange: (changes: Record<string, string | null>) => void;
	} = $props();
	const presets = [
		{ value: '30', label: 'Last 30 days' }, { value: '90', label: 'Last 90 days' },
		{ value: '365', label: 'Last 365 days' }, { value: 'year', label: 'This year' },
		{ value: 'last-year', label: 'Last year' }, { value: 'all', label: 'All time' }
	];
	const wide = new MediaQuery('(min-width: 800px)');
	let open = $state(false);
	let draft = $state<DateRange>({ start: undefined, end: undefined });
	let placeholder = $state<DateValue>(parseDate(dayKey(new Date())));
	let fromInput = $state('');
	let toInput = $state('');
	let calendarVersion = $state(0);
	const valid = $derived(customRange(fromInput, toInput, now));
	const label = $derived(presets.find((preset) => preset.value === range)?.label
		?? `${from.toLocaleDateString(undefined, { dateStyle: 'medium' })} – ${to.toLocaleDateString(undefined, { dateStyle: 'medium' })}`);

	function opened(value: boolean) {
		if (!value) return;
		fromInput = dayKey(from); toInput = dayKey(to);
		draft = { start: parseDate(fromInput), end: parseDate(toInput) };
		placeholder = draft.start!;
		calendarVersion += 1;
	}
	function typed(field: 'from' | 'to', value: string) {
		if (field === 'from') fromInput = value;
		else toInput = value;
		const selection = customRange(fromInput, toInput, now);
		if (!selection) return;
		draft = { start: parseDate(fromInput), end: parseDate(toInput) };
		placeholder = draft.start!;
		calendarVersion += 1;
	}
	function apply() {
		if (!valid) return;
		onchange({ range: 'custom', from: fromInput, to: toInput, period: null });
		open = false;
	}
</script>

<Popover.Root bind:open onOpenChange={opened}>
	<Popover.Trigger class="choice-trigger date-range-trigger" aria-label="Date range"><CalendarDays size={15} /><span>{label}</span></Popover.Trigger>
	<Popover.Portal>
		<Popover.Content class="date-range-popover" sideOffset={7} align="end" collisionPadding={12}>
			<div class="date-presets" aria-label="Date range presets">
				{#each presets as preset}<button class:active={range === preset.value} onclick={() => { onchange({ range: preset.value, from: null, to: null, period: null }); open = false; }}>{preset.label}</button>{/each}
			</div>
			<div class="date-custom">
				<div class="date-fields"><label>From<input type="date" aria-label="Range start" max={dayKey(now)} value={fromInput} onchange={(event) => typed('from', event.currentTarget.value)} /></label><label>To<input type="date" aria-label="Range end" min={fromInput} max={dayKey(now)} value={toInput} onchange={(event) => typed('to', event.currentTarget.value)} /></label></div>
				{#key calendarVersion}<RangeCalendar.Root value={draft} bind:placeholder weekStartsOn={1} weekdayFormat="short" numberOfMonths={wide.current ? 2 : 1} maxValue={parseDate(dayKey(now))} preventDeselect
					onValueChange={(value) => { draft = value; if (value.start && value.end) { fromInput = value.start.toString(); toInput = value.end.toString(); } }}
					onStartValueChange={(value) => { fromInput = value?.toString() || ''; }} onEndValueChange={(value) => { toInput = value?.toString() || ''; }}>
					{#snippet children({ months, weekdays })}
						<RangeCalendar.Header class="calendar-nav"><RangeCalendar.PrevButton class="icon-button" aria-label="Previous month"><ChevronLeft size={16} /></RangeCalendar.PrevButton><div class="calendar-selects"><RangeCalendar.MonthSelect aria-label="Calendar month" /><RangeCalendar.YearSelect aria-label="Calendar year" /></div><RangeCalendar.Heading class="sr-only" /><RangeCalendar.NextButton class="icon-button" aria-label="Next month"><ChevronRight size={16} /></RangeCalendar.NextButton></RangeCalendar.Header>
						<div class="calendar-months">
							{#each months as month (month.value.toString())}
								<div class="calendar-month"><div class="calendar-caption">{month.value.toDate(getLocalTimeZone()).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</div>
									<RangeCalendar.Grid><RangeCalendar.GridHead><RangeCalendar.GridRow>{#each weekdays as weekday}<RangeCalendar.HeadCell>{weekday.slice(0, 2)}</RangeCalendar.HeadCell>{/each}</RangeCalendar.GridRow></RangeCalendar.GridHead>
										<RangeCalendar.GridBody>{#each month.weeks as week}<RangeCalendar.GridRow>{#each week as date}<RangeCalendar.Cell {date} month={month.value}><RangeCalendar.Day /></RangeCalendar.Cell>{/each}</RangeCalendar.GridRow>{/each}</RangeCalendar.GridBody>
									</RangeCalendar.Grid>
								</div>
							{/each}
						</div>
					{/snippet}
				</RangeCalendar.Root>{/key}
				<div class="date-range-footer"><span>{valid ? 'Both dates are included.' : 'Choose a valid range ending today or earlier.'}</span><div><Popover.Close class="text-button">Cancel</Popover.Close><button class="primary-button" disabled={!valid} onclick={apply}>Apply range</button></div></div>
			</div>
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>
