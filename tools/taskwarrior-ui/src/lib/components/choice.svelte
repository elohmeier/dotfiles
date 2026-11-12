<script lang="ts">
	import { Select } from 'bits-ui';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	let { label, value, options, onchange }: {
		label: string; value: string; options: { value: string; label: string }[];
		onchange: (value: string) => void;
	} = $props();
</script>

<Select.Root type="single" {value} items={options} onValueChange={onchange}>
	<Select.Trigger class="choice-trigger" aria-label={label}>
		<span>{options.find((option) => option.value === value)?.label}</span><ChevronDown size={14} />
	</Select.Trigger>
	<Select.Portal>
		<Select.Content class="choice-content" sideOffset={5} align="end">
			<Select.Viewport>
				{#each options as option (option.value)}
					<Select.Item class="choice-item" value={option.value} label={option.label}>{option.label}</Select.Item>
				{/each}
			</Select.Viewport>
		</Select.Content>
	</Select.Portal>
</Select.Root>
