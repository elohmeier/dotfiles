# LayerChart Chart Patterns

Use this reference for concrete chart setup and composition patterns.

## Installation

For an app:

```sh
npm install layerchart
```

Install D3 packages used by the chart, for example:

```sh
npm install d3-scale d3-array d3-shape d3-scale-chromatic
```

Tailwind projects must scan LayerChart components:

```js
export default {
  content: [
    "./src/**/*.{html,svelte}",
    "./node_modules/svelte-ux/**/*.{svelte,js}",
    "./node_modules/layerchart/**/*.{svelte,js}",
  ],
};
```

If the app does not use the Svelte UX/LayerStack theme tokens used in docs, replace classes like
`stroke-primary`, `fill-secondary`, or `hsl(var(--color-primary))` with app-specific colors.

## Wrapper Charts

Use wrappers for standard charts. They create `Chart`, render layers, axes, grid/rules, tooltip,
highlight, legend, and labels according to props.

### Line Chart

```svelte
<script lang="ts">
import { scaleTime } from "d3-scale";
import { LineChart } from "layerchart";
</script>

<div class="h-[300px]">
  <LineChart
    data={rows}
    x="date"
    xScale={scaleTime()}
    y="value"
    yDomain={[0, null]}
    yNice
    points
    props={{
      spline: { class: "stroke-2" },
      yAxis: { format: "metric" },
    }}
  />
</div>
```

### Bar Chart

```svelte
<script lang="ts">
import { BarChart } from "layerchart";
</script>

<div class="h-[300px]">
  <BarChart
    data={rows}
    x="category"
    y="value"
    labels
    props={{
      bars: { class: "fill-primary", radius: 4, rounded: "top" },
      yAxis: { format: "metric" },
    }}
  />
</div>
```

Horizontal bars:

```svelte
<BarChart data={rows} x="value" y="category" orientation="horizontal" />
```

Grouped or stacked series:

```svelte
<BarChart
  data={rows}
  x="year"
  y="value"
  series={[
    { key: "apples", label: "Apples", color: "#ef4444" },
    { key: "bananas", label: "Bananas", color: "#eab308" },
  ]}
  seriesLayout="stack"
  legend
/>
```

Series values default to `s.key`; use `value` when each series maps to a different accessor.

### Area Chart

```svelte
<AreaChart
  data={rows}
  x="date"
  xScale={scaleTime()}
  y="value"
  yDomain={[0, null]}
  yNice
  points
  props={{
    area: {
      class: "fill-primary/30",
      line: { class: "stroke-primary stroke-2" },
    },
  }}
/>
```

Use `seriesLayout="stack"`, `stackExpand`, or `stackDiverging` for stacked areas.

### Pie/Donut Chart

```svelte
<PieChart
  data={rows}
  key="id"
  label="name"
  value="amount"
  innerRadius={60}
  cornerRadius={2}
  legend
/>
```

### Scatter Chart

```svelte
<ScatterChart
  data={rows}
  x="x"
  y="y"
  r="size"
  props={{ points: { class: "stroke-surface-content/40", fillOpacity: 0.3 } }}
/>
```

For grouped scatter colors, pass `series` with per-series `data` and `color`, then enable `legend`.

## Low-level Chart

Use `Chart` plus marks when the chart needs custom composition.

```svelte
<script lang="ts">
import { scaleTime } from "d3-scale";
import {
  Axis,
  Chart,
  Highlight,
  LinearGradient,
  Spline,
  Svg,
  Tooltip,
} from "layerchart";
</script>

<div class="h-[320px]">
  <Chart
    data={rows}
    x="date"
    xScale={scaleTime()}
    y="value"
    yDomain={[0, null]}
    yNice
    padding={{ left: 16, bottom: 24 }}
    tooltip={{ mode: "bisect-x" }}
  >
    <Svg>
      <Axis placement="left" grid rule />
      <Axis placement="bottom" rule />
      <LinearGradient class="from-blue-500 to-red-500" vertical let:gradient>
        <Spline stroke={gradient} class="stroke-2" />
      </LinearGradient>
      <Highlight points lines />
    </Svg>

    <Tooltip.Root let:data>
      <Tooltip.List>
        <Tooltip.Item label="value" value={data.value} />
      </Tooltip.List>
    </Tooltip.Root>
  </Chart>
</div>
```

Use simpler explicit gradient stops if `scale.ticks()` is not available for the chosen scale.

## Render Layers

- `Svg`: best for axes, normal mark counts, text, accessibility, hoverable DOM elements.
- `Canvas`: best for many marks, dense maps, or expensive paths.
- `Html`: place regular HTML within chart coordinates or pan/zoom containers.
- Layers can be mixed. A common pattern is SVG axes plus Canvas marks.
- Pass `pointerEvents={false}` to a non-interactive layer that should not intercept input.

## Scales And Domains

Date/time axes:

```svelte
<Chart data={rows} x="date" xScale={scaleTime()} y="value" />
```

Categorical axis:

```svelte
<Chart data={rows} x="category" xScale={scaleBand().padding(0.4)} y="value" />
```

Color encoding:

```svelte
<Chart
  data={rows}
  c="group"
  cScale={scaleOrdinal()}
  cDomain={["a", "b", "c"]}
  cRange={["#2563eb", "#16a34a", "#f97316"]}
>
  <Svg>
    <Points />
  </Svg>
</Chart>
```

Threshold color encoding:

```svelte
<Chart
  data={rows}
  c="value"
  cScale={scaleThreshold()}
  cDomain={[50, 90]}
  cRange={["#ef4444", "#eab308", "#22c55e"]}
>
  <Svg><Points /></Svg>
</Chart>
```

## Multi-series Patterns

Wrapper `series` works well for wide data:

```svelte
<LineChart
  data={rows}
  x="date"
  series={[
    { key: "revenue", label: "Revenue", color: "#2563eb" },
    { key: "cost", label: "Cost", color: "#ef4444" },
  ]}
  legend
/>
```

For long-form data, group outside the chart and render one mark per group:

```svelte
<Chart
  data={flatRows}
  x="date"
  xScale={scaleTime()}
  y="value"
  c="series"
  let:cScale
>
  <Svg>
    {#each groups as [name, seriesRows]}
      {@const color = cScale?.(name)}
      <Spline data={seriesRows} stroke={color} class="stroke-2" />
    {/each}
  </Svg>
</Chart>
```

Use `pivotLonger(wideRows, keys, 'series', 'value')` when long-form data is easier.

## Slots And Custom Marks

LayerChart docs currently show Svelte legacy component syntax with `export let`, `let:` slot props,
and `<svelte:fragment slot="...">`. Match the syntax style used by the target app.

Wrapper charts expose useful slots such as `marks`, `belowMarks`, and tooltip content. Verify exact
slot names in the wrapper source before using them.

Example overriding BarChart marks:

```svelte
<BarChart data={rows} x="date" y="value">
  <svelte:fragment slot="marks" let:series let:getBarsProps>
    {#each series as s, i (s.key)}
      <Bars {...getBarsProps(s, i)} class="fill-primary" />
    {/each}
  </svelte:fragment>
</BarChart>
```
