<script lang="ts">
	import { Combobox } from 'bits-ui';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import Check from '@lucide/svelte/icons/check';
	let { label, value, options, onchange }: {
		label: string; value: string; options: { value: string; label: string; count?: number }[];
		onchange: (value: string) => void;
	} = $props();
	let query = $state('');
	let open = $state(false);
	const selected = $derived(options.find((option) => option.value === value)?.label || value);
	const filtered = $derived(options.filter((option) => option.label.toLocaleLowerCase().includes(query.toLocaleLowerCase())));
</script>

<Combobox.Root type="single" {value} items={options} bind:open inputValue={open ? query : selected} allowDeselect={false} onValueChange={onchange} onOpenChange={(value) => { if (!value) query = ''; }}>
	<div class="search-choice">
		<Combobox.Input aria-label={label} placeholder={`Search ${label.toLowerCase()}…`} onfocus={() => { query = ''; open = true; }} oninput={(event) => { query = event.currentTarget.value; open = true; }} />
		<Combobox.Trigger class="icon-button" aria-label={`Show ${label.toLowerCase()} options`}><ChevronDown size={14} /></Combobox.Trigger>
	</div>
	<Combobox.Portal>
		<Combobox.Content class="choice-content search-choice-content" sideOffset={5} align="start">
			<Combobox.Viewport>
				{#each filtered as option (option.value)}
					<Combobox.Item class="choice-item search-choice-item" value={option.value} label={option.label}>
						<span>{option.label}</span>{#if option.count !== undefined}<small>{option.count}</small>{/if}{#if option.value === value}<Check size={13} />{/if}
					</Combobox.Item>
				{:else}<p class="picker-empty">No matches</p>{/each}
			</Combobox.Viewport>
		</Combobox.Content>
	</Combobox.Portal>
</Combobox.Root>
