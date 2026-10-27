# LayerChart Debugging And Performance

Use this reference when a chart is blank, incorrect, slow, or visually broken.

## Blank Or Invisible Chart

Check these first:

- The chart wrapper has a real height, for example `class="h-[300px]"`.
- The chart is inside a visible parent, not an unmeasured hidden tab.
- Marks are inside `Svg`, `Canvas`, or `Html`.
- Data is non-empty and accessors match field names exactly.
- Time data is `Date` objects when using `scaleTime()`, not raw strings unless converted.
- Domains are not invalid, for example `[undefined, undefined]`.
- Categorical data uses `scaleBand()` where needed.
- Tailwind did not purge LayerChart classes; include `./node_modules/layerchart/**/*.{svelte,js}`.
- Theme classes from docs are available, or replaced with explicit colors.
- SSR did not try to render browser-only code; consider `ssr={false}` only when needed.

Useful temporary diagnostics:

```svelte
<Chart debug data={rows} x="date" y="value">...</Chart>
<Tooltip.Context debug mode="voronoi" />
```

## Wrong Axis Or Scale

Symptoms and fixes:

- Date axis looks numeric: pass `xScale={scaleTime()}` and ensure values are `Date`.
- Bars overlap or have no width: use `scaleBand().padding(...)` on categorical axis.
- Quantitative chart does not start at zero: use `yDomain={[0, null]}` or `yBaseline={0}`.
- Negative bars/areas clipped incorrectly: use baseline props or explicit domains that include zero.
- Labels/ticks overlap: adjust `padding`, reduce ticks, rotate labels, or use explicit `ticks`.
- Horizontal bars reversed unexpectedly: check `orientation`, `x`/`y` accessors, and y band scale.

## Tooltip Problems

- Tooltip never appears: confirm `tooltip={{ mode: ... }}` is on `Chart` and pointer events are not
  disabled.
- Tooltip data is wrong on a line: `bisect-x` expects data sorted by x.
- Tooltip misses scatter points: use `voronoi` or `quadtree` and set an appropriate `radius`.
- Bars need band interaction: use `band` or `bounds`, not `bisect-x`.
- Tooltip hides when moving into custom content: use `locked` or `hideDelay`.
- Highlight does not show: highlight depends on tooltip context data.

## Canvas And Pointer Events

- Canvas is faster for many marks, dense paths, or map features.
- SVG is better for axes, labels, DOM interaction, and small-to-medium mark counts.
- Mixed layers are normal: SVG axes plus Canvas marks is a standard approach.
- Use `pointerEvents={false}` on background/non-interactive layers so foreground interactions work.
- For geo tooltips over dense canvas features, consider a separate hover/highlight layer.

## Performance Patterns

Choose based on data size and visual needs:

- Few to thousands of marks: SVG is often fine and easiest to debug.
- Many points/paths: use `Canvas`, simplify data, or pre-aggregate.
- Very wide data: inspect performance examples under `docs/performance`.
- Repeated computed transforms: precompute derived rows outside render where practical.
- Maps: simplify TopoJSON/GeoJSON, render base geography in Canvas, keep labels sparse.
- Tooltip nearest-neighbor search: prefer `quadtree` or `voronoi` over manual scanning.
- Avoid animating thousands of individual SVG elements unless necessary.

Performance docs in this repo:

- `packages/layerchart/src/routes/docs/performance/wide_data/+page.svelte`
- `packages/layerchart/src/routes/docs/performance/wide_data_processed/+page.svelte`
- `packages/layerchart/src/routes/docs/performance/series_arrays/+page.svelte`
- `packages/layerchart/src/routes/docs/performance/dimension_arrays/+page.svelte`
- `packages/layerchart/src/routes/docs/performance/dimension_arrays_processed/+page.svelte`

## TypeScript And Svelte Checks

In the LayerChart repo:

```sh
pnpm --filter layerchart check
pnpm --filter layerchart test:unit
pnpm --filter layerchart build
```

In an app, use the app's commands, typically:

```sh
pnpm check
pnpm build
```

If a prop fails type checking, inspect the component source `export let` and wrapper `props` object.
Many nested customizations must be passed under the wrapper's `props` prop instead of directly on the
wrapper.

## Visual QA Checklist

Before finalizing user-facing chart work:

- The chart is nonblank at target sizes.
- Axes, grid, and rules align with marks.
- Labels and tooltip content do not overflow or overlap important data.
- Tooltip follows the expected data point or band.
- Keyboard/focus and pointer behavior are acceptable for the app's needs.
- Colors work in the app theme and maintain readable contrast.
- Canvas/SVG layers do not block each other's pointer events.
- The chart handles empty or small datasets gracefully if that state is possible.
