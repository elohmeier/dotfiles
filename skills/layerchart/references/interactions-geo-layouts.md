# LayerChart Interactions, Geo, And Layouts

Use this reference for interactivity and non-Cartesian charts.

## Tooltips

Enable tooltip data lookup on `Chart`:

```svelte
<Chart data={rows} x="date" y="value" tooltip={{ mode: "bisect-x" }}>
  <Svg>
    <Spline />
    <Highlight points lines />
  </Svg>

  <Tooltip.Root let:data>
    <Tooltip.Header>{data.label}</Tooltip.Header>
    <Tooltip.List>
      <Tooltip.Item label="value" value={data.value} format="integer" />
    </Tooltip.List>
  </Tooltip.Root>
</Chart>
```

Mode selection:

- `bisect-x`: line/area charts over sorted x data, especially time series.
- `bisect-y`: horizontal continuous-axis interaction.
- `band`: bar charts with a categorical band axis.
- `bisect-band`: data within a categorical band.
- `bounds`: interval-like records or rectangular hit testing.
- `voronoi`: nearest point, multi-series, scatter, non-monotonic data.
- `quadtree`: nearest point for larger point clouds.
- `manual`: explicitly call tooltip context methods.

Helpful props:

- `findTooltipData`: `'closest'`, `'left'`, or `'right'` for bisect modes.
- `raiseTarget`: raise hovered SVG node.
- `locked`: keep tooltip fixed for clickable content.
- `radius`: quadtree search radius.
- `debug`: show hit targets.
- `hideDelay`: delay hiding.

Bind or consume tooltip context when needed:

```svelte
<script lang="ts">
import { Chart } from "layerchart";
import type { ComponentProps } from "svelte";

let tooltipContext: ComponentProps<Chart<any>>["tooltipContext"];
</script>

<Chart bind:tooltipContext tooltip={{ mode: "bisect-x" }}>...</Chart>
```

## Highlights

`Highlight` renders visual feedback based on active tooltip data:

```svelte
<Highlight points lines />
<Highlight area />
<Highlight bar={{ class: "fill-primary", strokeWidth: 1 }} />
```

Use `axis="x"`, `axis="y"`, `axis="both"`, or `axis="none"` when the highlight should snap or draw
on a particular axis. Use `onareaclick`, `onbarclick`, `onpointclick`, `onpointenter`, and
`onpointleave` for interactions.

## Brush

Wrapper charts support brush props for selection/zoom workflows:

```svelte
<LineChart
  data={rows}
  x="date"
  y="value"
  brush
  bind:xDomain
/>
```

For custom charts, pass `brush` to `Chart` and use `let:brush` or `bind:brushContext`. Check
`BrushContext.svelte` before using advanced props; there are integrated and external brush modes.

## Pan And Zoom

Use `transform` on `Chart`:

```svelte
<script lang="ts">
import { cubicOut } from "svelte/easing";
</script>

<Chart
  data={rows}
  x="x"
  y="y"
  transform={{
    mode: "canvas",
    initialScrollMode: "scale",
    tweened: { duration: 800, easing: cubicOut },
  }}
>
  <Svg>
    <Points />
  </Svg>
</Chart>
```

Modes:

- `none`: no transform.
- `canvas`: scale/translate render layers as a canvas-like viewport.
- `manual`: transform context exists, but components decide how to apply it.

Useful imperative methods from `transformContext`:

- `reset()`
- `zoomIn()`
- `zoomOut()`
- `translateCenter()`
- `zoomTo(center, rect?)`
- `setScale(value)`
- `setTranslate(point)`
- `setScrollMode('scale' | 'translate' | 'none')`

## Geo Charts

Use `Chart` with `geo` options and geo marks:

```svelte
<script lang="ts">
import { geoMercator } from "d3-geo";
import { Chart, GeoPath, Graticule, Svg, Tooltip } from "layerchart";
</script>

<div class="h-[420px]">
  <Chart
    geo={{
      projection: geoMercator,
      fitGeojson: land,
      applyTransform: ["scale", "translate"],
    }}
    transform={{ mode: "manual", initialScrollMode: "scale" }}
    let:tooltip
  >
    <Svg>
      <Graticule class="stroke-surface-content/20" />
      <GeoPath
        geojson={land}
        class="fill-surface-200 stroke-surface-content/30"
      />
      {#each countries.features as feature}
        <GeoPath
          geojson={feature}
          class="fill-primary/30 stroke-primary"
          {tooltip}
        />
      {/each}
    </Svg>

    <Tooltip.Root let:data>
      <Tooltip.Header>{data.properties.name}</Tooltip.Header>
    </Tooltip.Root>
  </Chart>
</div>
```

Geo components:

- `GeoPath`: draw GeoJSON/TopoJSON-derived features.
- `GeoPoint`: draw projected longitude/latitude points.
- `GeoCircle`: draw geographic circles.
- `GeoSpline`: draw projected lines/arcs.
- `GeoTile` and `TileImage`: tiled maps.
- `GeoVisible`: conditionally render when coordinates/features are visible.
- `Graticule`: projection grid.
- `GeoEdgeFade`: fade near projection edge.

Geo examples to inspect:

- `GeoPath`, `GeoPoint`, `GeoTile`, `GeoProjection`
- `Choropleth`, `BubbleMap`, `SpikeMap`
- `ZoomableMap`, `ZoomableTileMap`
- globe examples such as `AnimatedGlobe`, `EarthquakeGlobe`, `SubmarineCablesGlobe`

Geo debugging:

- Verify coordinate order is `[longitude, latitude]`.
- Verify the projection function is passed, for example `projection: geoMercator`, not an already
  misconfigured projection unless intended.
- Use `fitGeojson` for fitting, then `applyTransform` for pan/zoom or rotation behavior.
- For dense maps, render features in `Canvas` and keep tooltips/highlights in `Svg` or a separate
  layer.

## Hierarchy

Hierarchy layouts usually pass a `d3-hierarchy` root or hierarchical data to `Chart`, then render
layout components:

- `Pack`: packed circles.
- `Tree`: node-link tree.
- `Treemap`: nested rectangles.
- `Partition`: partition layout; combine with `Arc`/`Pie` patterns for sunburst.

Examples to inspect: `Pack`, `Partition`, `Sunburst`, `Tree`, `Treemap`.

Common guidance:

- Prepare hierarchy with `d3-hierarchy` when the example does.
- Set explicit chart dimensions or an aspect-ratio wrapper.
- Use `let:tooltip` and opacity/highlight logic for hover focus in dense hierarchies.

## Graph And Force

Graph/layout components:

- `Sankey`: flow diagrams; data is a Sankey graph with nodes and links.
- `Dagre`: directed graph layout.
- `ForceSimulation`: force-directed node/link layouts.

Utilities:

- `graphFromCsv`
- `graphFromHierarchy`
- `graphFromNode`
- `nodesFromLinks`
- `ancestors`
- `descendants`

Examples to inspect:

- `Sankey`, `Dagre`
- `ForceGraph`, `ForceDrag`, `ForceTree`, `ForceGroup`, `ForceDisjointGraph`,
  `ForceLattice`, `ForceText`, `Beeswarm`, `CollisionDetection`

For graph work, prefer the existing LayerChart example closest to the requested behavior, because
node/link shape and simulation props are easy to misremember.
