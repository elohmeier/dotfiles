# LayerChart API Map

Use this reference to locate source, docs, examples, and prop definitions.

## Source Of Truth

In the LayerChart repository:

- public exports: `packages/layerchart/src/lib/index.ts`
- component exports: `packages/layerchart/src/lib/components/index.ts`
- chart wrapper exports: `packages/layerchart/src/lib/components/charts/index.ts`
- tooltip namespace exports: `packages/layerchart/src/lib/components/tooltip/index.ts`
- utility exports: `packages/layerchart/src/lib/utils/index.ts`
- component docs: `packages/layerchart/src/routes/docs/components/<Component>/+page.svelte`
- examples: `packages/layerchart/src/routes/docs/examples/<Example>/+page.svelte`
- setup docs: `packages/layerchart/src/routes/getting-started/+page.svelte`

In an app consuming LayerChart:

- check `package.json` for `layerchart`, `svelte`, D3 packages, and Tailwind setup
- inspect existing chart code before changing conventions
- check `node_modules/layerchart/dist/**/*.d.ts` if source docs are unavailable

Useful commands:

```sh
rg -n "from 'layerchart'|from \"layerchart\"" src packages -g '*.svelte' -g '*.ts'
rg -n "^\\s*export let " packages/layerchart/src/lib/components/Chart.svelte
rg -n "<Tooltip|tooltip=|<Highlight" packages/layerchart/src/routes/docs -g '*.svelte'
rg -n "<Geo|geo=|projection" packages/layerchart/src/routes/docs -g '*.svelte'
```

## Exported Components

High-level charts:

- `AreaChart`, `BarChart`, `LineChart`, `PieChart`, `ScatterChart`

Chart shell and render layers:

- `Chart`, `Svg`, `Canvas`, `Html`, `WebGL`

Common chart structure:

- `Axis`, `Frame`, `Grid`, `Legend`, `Rule`, `Bounds`, `ChartClipPath`

Marks:

- `Area`, `Bar`, `Bars`, `Calendar`, `Circle`, `Hull`, `Labels`, `Line`, `Link`, `Pie`,
  `Point`, `Points`, `Rect`, `Spline`, `Text`, `Threshold`

Interactions:

- `BrushContext`, `Highlight`, `Tooltip`, `TransformContext`, `Voronoi`

Geo:

- `GeoContext`, `GeoCircle`, `GeoEdgeFade`, `GeoPath`, `GeoPoint`, `GeoSpline`, `GeoTile`,
  `GeoVisible`, `Graticule`, `TileImage`

Layout:

- `Dagre`, `ForceSimulation`, `Pack`, `Partition`, `Sankey`, `Tree`, `Treemap`

SVG utilities:

- `Arc`, `Blur`, `ClipPath`, `CircleClipPath`, `ColorRamp`, `Group`, `LinearGradient`,
  `Marker`, `MotionPath`, `Pattern`, `RadialGradient`, `RectClipPath`

Tooltip namespace:

- `Tooltip.Root`, `Tooltip.Context`, `Tooltip.Header`, `Tooltip.Item`,
  `Tooltip.List`, `Tooltip.Separator`

## Utility Exports

Common utilities:

- `accessor(prop)`: normalizes string/function/number/array accessors.
- `chartDataArray(data)`: returns flat chart data for arrays and supported structured data.
- `defaultChartPadding(axis, legend)`: wrapper chart padding helper.
- `findRelatedData(data, original, accessor)`: finds data related by accessor.

Data transforms:

- `pivotLonger(data, columns, name, value)`
- `pivotWider(data, column, name, value)`
- `groupStackData(data, options)`
- `stackOffsetSeparated(series, order)`

Geo/graph/hierarchy helpers:

- `geoCurvePath`, `antipode`, `isVisible`, `geoFitObjectTransform`
- `graphFromCsv`, `graphFromHierarchy`, `graphFromNode`, `nodesFromLinks`, `ancestors`,
  `descendants`
- `findAncestor`

Path/tick/threshold helpers:

- `getEasingPath`, `circlePath`, `spikePath`, `flattenPathData`
- `thresholdTime`, `thresholdChunks`
- `getMajorTicks`, `formatMajorTick`, `getMinorTicks`

## Documentation Pages

Component docs are organized by category:

- Charts: `Chart`, `AreaChart`, `BarChart`, `LineChart`, `PieChart`, `ScatterChart`
- Common: `Axis`, `Frame`, `Grid`, `Legend`, `Rule`
- Primitives: `Arc`, `Bar`, `Circle`, `Group`, `Line`, `Marker`, `Point`, `Rect`, `Text`
- Marks: `Area`, `Bars`, `Calendar`, `Hull`, `Labels`, `Link`, `Pie`, `Points`, `Spline`,
  `Threshold`
- Interactions: `BrushContext`, `Highlight`, `Tooltip`, `TooltipContext`,
  `TransformContext`, `Voronoi`
- Geo: `GeoContext`, `GeoCircle`, `GeoEdgeFade`, `GeoPath`, `GeoPoint`, `GeoSpline`,
  `GeoTile`, `GeoVisible`, `Graticule`, `TileImage`
- Layout: `ForceSimulation`, `Pack`, `Partition`, `Sankey`, `Tree`, `Treemap`
- Clipping: `ClipPath`, `ChartClipPath`, `CircleClipPath`, `RectClipPath`
- Other: `Blur`, `Bounds`, `ColorRamp`, `LinearGradient`, `RadialGradient`, `MotionPath`,
  `Pattern`

Example docs are organized by chart family:

- Cartesian/polar: `Area`, `Bars`, `Columns`, `Candlestick`, `Compound`, `DotPlot`,
  `DualAxis`, `Histogram`, `Line`, `Oscilloscope`, `PunchCard`, `RadialLine`, `Scatter`,
  `Sparkbar`, `Sparkline`, `Threshold`, `Arc`
- Hierarchy: `Pack`, `Partition`, `Sunburst`, `Tree`, `Treemap`
- Graph: `Dagre`, `Sankey`
- Force: `Beeswarm`, `CollisionDetection`, `ForceDisjointGraph`, `ForceDrag`, `ForceGraph`,
  `ForceGroup`, `ForceLattice`, `ForceTree`, `ForceText`
- Geo: `GeoPath`, `GeoPoint`, `GeoTile`, `GeoProjection`, `StateMap`, `CountryMap`,
  `Choropleth`, `BubbleMap`, `SpikeMap`, `ZoomableMap`, `ZoomableTileMap`, `Timezones`,
  `AnimatedGlobe`, `TranslucentGlobe`, `SketchyGlobe`, `EarthquakeGlobe`,
  `SubmarineCablesGlobe`, `EclipsesGlobe`, `LoftedArcs`

## Wrapper Chart Props To Check First

All wrappers extend many `Chart` props, including data/accessors/scales/domains/ranges, `tooltip`,
`brush`, `transform`, `geo`, `padding`, `debug`, and event callbacks.

Wrapper-specific common props:

- `BarChart`: `orientation`, `series`, `seriesLayout`, `axis`, `rule`, `grid`, `labels`,
  `legend`, `bandPadding`, `groupPadding`, `stackPadding`, `props`, `renderContext`,
  `onbarclick`, `ontooltipclick`
- `LineChart`: `series`, `axis`, `brush`, `grid`, `labels`, `legend`, `points`, `rule`,
  `props`, `renderContext`, `onpointclick`, `ontooltipclick`
- `AreaChart`: similar to `LineChart`, plus `seriesLayout`
- `ScatterChart`: `series`, `axis`, `brush`, `grid`, `labels`, `legend`, `rule`, `props`,
  `renderContext`
- `PieChart`: `key`, `label`, `value`, `c`, `series`, `legend`, `range`, `innerRadius`,
  `outerRadius`, `cornerRadius`, `padAngle`, `placement`, `center`, `props`, `renderContext`,
  `onarcclick`

## Prop Lookup Pattern

When uncertain:

1. Open the wrapper/component `.svelte` source.
2. Read `interface $$Props` and `export let` declarations.
3. Check the docs page for runnable examples.
4. Check examples for composition details or slots.
5. Check `.d.ts` output only if source is unavailable.

Never rely on guessed prop names for chart internals. LayerChart has specific nested `props` objects
for wrappers, for example `props={{ bars: {...}, xAxis: {...}, tooltip: {...} }}`.
