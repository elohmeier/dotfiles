---
name: layerchart
description: Use when helping users build, customize, debug, or review LayerChart visualizations in Svelte, including installation, Chart setup, high-level chart components, composable marks, axes, scales, tooltips, highlights, brushing, pan/zoom, geo maps/projections, hierarchy or graph layouts, utilities, performance, and LayerChart repository docs/examples.
---

# LayerChart

Use this skill for LayerChart user work: creating charts, translating examples, choosing components,
debugging rendering issues, adding interactions, and explaining LayerChart APIs.

LayerChart is a composable Svelte charting library built on Layer Cake. It exposes both:

- high-level chart components: `AreaChart`, `BarChart`, `LineChart`, `PieChart`, `ScatterChart`
- low-level building blocks: `Chart`, render layers (`Svg`, `Canvas`, `Html`), axes, marks, geo,
  hierarchy/graph layouts, interactions, and utilities

## First Moves

1. Identify whether the user needs a quick chart, a custom composition, an interaction, a geo/layout
   chart, performance help, or debugging.
2. Prefer local project context over memory. Inspect imports, installed version, Svelte version,
   existing chart style, and nearby examples before writing code.
3. Use LayerChart's own docs/examples as the source of truth when available:
   `packages/layerchart/src/routes/docs/...` in this repo, or the installed package/source in an app.
4. Do not invent props. Verify non-obvious props from component source or generated `.d.ts` files.
5. Run the project's normal Svelte/TypeScript check after changes when feasible.

Useful local lookup commands:

```sh
rg -n "export let|interface \\$\\$Props" packages/layerchart/src/lib/components -g '*.svelte'
rg -n "<Chart|<LineChart|<BarChart|<Tooltip|<Geo" packages/layerchart/src/routes/docs -g '*.svelte'
skills/layerchart/scripts/find-layerchart-docs.sh tooltip
```

## Reference Loading

Load only the reference needed for the task:

- `references/api-map.md`: component catalog, docs paths, exports, and lookup workflow.
- `references/chart-patterns.md`: installation, wrapper charts, low-level `Chart`, scales, series,
  styling, and composition snippets.
- `references/interactions-geo-layouts.md`: tooltips, highlights, brush, transform/pan-zoom, geo,
  hierarchy, graph, and force layouts.
- `references/debugging-performance.md`: common bugs, performance choices, and verification.

## Core Model

Every custom LayerChart composition usually has this shape:

```svelte
<script lang="ts">
import { scaleTime } from "d3-scale";
import { Axis, Chart, Highlight, Spline, Svg, Tooltip } from "layerchart";
</script>

<div class="h-[300px]">
  <Chart
    data={data}
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
      <Spline class="stroke-2 stroke-primary" />
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

Key implications:

- The wrapper element needs a real height. Blank charts often come from a zero-height parent.
- Import LayerChart components from `layerchart`; import D3 scales/shapes from D3 packages.
- Use `x`, `y`, `z`, `r`, and `c` accessors as strings, functions, numbers, or accessor arrays.
- Use D3 scale instances for non-default scale behavior, especially `scaleTime()` and `scaleBand()`.
- Use `yDomain={[0, null]}` or `yBaseline={0}` to anchor quantitative charts at zero.
- Put visible marks inside `Svg`, `Canvas`, or `Html`. Mixed render layers are allowed.
- `Chart` slot props expose scales, dimensions, `tooltip`, `brush`, `projection`, color scales, and
  transforms for advanced composition.

## Component Choice

Prefer wrappers when the desired chart matches their API:

- `BarChart`: vertical/horizontal bars, grouped/stacked bars, labels, legend, grid, tooltip.
- `LineChart` and `AreaChart`: time or numeric series, multi-series, brush, points, labels, radial.
- `ScatterChart`: x/y points, color/radius encodings, labels, brush.
- `PieChart`: pie/donut charts with legend and tooltip.

Use low-level `Chart` plus marks when the chart is compound, needs custom slots, uses multiple mark
types, custom axes, special scales, custom tooltip behavior, canvas/SVG layering, geo, hierarchy,
graph, animation, or unusual data transforms.

## Styling And Data

- LayerChart examples use Tailwind classes and theme tokens like `stroke-primary` or
  `hsl(var(--color-primary))`. In apps without that theme, use explicit CSS colors or the app's
  design tokens.
- During installation, add `./node_modules/layerchart/**/*.{svelte,js}` to Tailwind content so
  component classes are retained.
- Examples often omit imports in rendered snippets; inspect full page source when copying.
- For wide data, use `series` on chart wrappers or `pivotLonger` for long-form data.
- For stacked/grouped bars, use `BarChart` `seriesLayout` or the utility `groupStackData`.

## Interactions

Common tooltip modes:

- line/area over sorted x data: `tooltip={{ mode: 'bisect-x' }}`
- horizontal categorical bars: `tooltip={{ mode: 'band' }}`
- scatter or multi-series nearest point: `tooltip={{ mode: 'voronoi' }}` or `quadtree`
- custom/manual behavior: bind `tooltipContext` or use `Tooltip.Context`

Highlight marks generally need an active tooltip context:

```svelte
<Chart tooltip={{ mode: "bisect-x" }}>
  <Svg>
    <Spline />
    <Highlight points lines />
  </Svg>
  <Tooltip.Root let:data>...</Tooltip.Root>
</Chart>
```

For pan/zoom, pass `transform` to `Chart` and optionally bind `transformContext` for imperative
controls. For maps, `geo.applyTransform` can connect pan/zoom or globe rotation to the projection.

## Verification

After code changes in this repo, prefer:

```sh
pnpm --filter layerchart check
pnpm --filter layerchart test:unit
```

For application changes, run the app's Svelte check/build command. For visual changes, start the dev
server and inspect the chart at realistic desktop and mobile sizes; verify nonblank rendering,
tooltip behavior, axes, labels, and overflow.
