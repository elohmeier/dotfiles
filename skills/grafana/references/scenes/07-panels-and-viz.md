# Panels and visualizations

`VizPanel` is the scene wrapper around any Grafana visualization plugin (timeseries, stat, table, etc.). `PanelBuilders` is a fluent helper that produces correctly-typed `VizPanel` instances.

## Contents

- [PanelBuilders — the fluent API](#panelbuilders--the-fluent-api)
- [Direct VizPanel construction](#direct-vizpanel-construction)
- [Table panel patterns](#table-panel-patterns)
- [Stat sparkline pattern](#stat-sparkline-pattern)
- [Panel menu](#panel-menu)
- [Header actions](#header-actions)
- [Panel context — sharing state across panels](#panel-context--sharing-state-across-panels)
- [Runtime panel plugins](#runtime-panel-plugins)
- [Subheader — adding content below the panel header](#subheader--adding-content-below-the-panel-header)
- [VizPanelExploreButton](#vizpanelexplorebutton)
- [Common gotchas](#common-gotchas)

## PanelBuilders — the fluent API

```ts
import { PanelBuilders } from "@grafana/scenes";

const panel = PanelBuilders.timeseries()
  .setTitle("HTTP requests")
  .setDescription("Rate of incoming requests")
  .setUnit("reqps")
  .setOption("legend", { displayMode: "list", placement: "right" })
  .setOption("tooltip", { mode: "multi", sort: "desc" })
  .setCustomFieldConfig("lineWidth", 2)
  .setCustomFieldConfig("fillOpacity", 10)
  .setColor({ mode: "palette-classic" })
  .setData(queryRunner)
  .setMin(0)
  .setMax(100)
  .setNoValue("-")
  .build();
```

Available builders (each returns a typed builder):

```
PanelBuilders.barchart()
PanelBuilders.bargauge()
PanelBuilders.canvas()
PanelBuilders.dashlist()
PanelBuilders.datagrid()
PanelBuilders.debug()
PanelBuilders.flamegraph()
PanelBuilders.gauge()
PanelBuilders.geomap()
PanelBuilders.heatmap()
PanelBuilders.histogram()
PanelBuilders.logs()
PanelBuilders.news()
PanelBuilders.nodegraph()
PanelBuilders.piechart()
PanelBuilders.stat()
PanelBuilders.statetimeline()
PanelBuilders.statushistory()
PanelBuilders.table()
PanelBuilders.text()
PanelBuilders.timeseries()
PanelBuilders.trend()
PanelBuilders.traces()
PanelBuilders.xychart()
```

`.build()` returns a `VizPanel<TOptions, TFieldConfig>`. The builder enforces types — `setOption('legend', ...)` for a `timeseries` panel is type-checked against the timeseries options interface.

### Common builder methods

```ts
// Display
.setTitle(string)
.setDescription(string)
.setDisplayMode('default' | 'transparent')
.setHoverHeader(boolean)
.setMenu(VizPanelMenu | undefined)

// Data wiring
.setData(SceneDataProvider)
.setTimeRange(SceneTimeRangeLike)

// Field config — defaults
.setUnit('bytes')
.setMin(0)
.setMax(100)
.setDecimals(2)
.setNoValue('-')
.setColor({ mode: 'palette-classic' })
.setMappings([{ type: 'value', options: { '0': { text: 'Off' } } }])
.setThresholds({ mode: 'absolute', steps: [...] })
.setLinks([{ title: 'Open', url: '/path?${__url.params}' }])

// Field config — custom (panel-specific)
.setCustomFieldConfig('lineWidth', 2)

// Field overrides — match fields and customize
.setOverrides((b) => b
  .matchFieldsWithName('errors')
  .overrideColor({ mode: 'fixed', fixedColor: 'red' })
  .overrideUnit('errs/s')
)

// Options (panel-specific)
.setOption('legend', { displayMode: 'list' })

// Behaviors (per-panel)
.setBehaviors([...])
.setHeaderActions([...])
```

## Direct VizPanel construction

For full control or runtime building, construct `VizPanel` directly:

```ts
import { VizPanel } from "@grafana/scenes";

new VizPanel({
  pluginId: "timeseries",
  title: "Custom panel",
  options: { legend: { displayMode: "list" } },
  fieldConfig: {
    defaults: {
      unit: "bytes",
      color: { mode: "palette-classic" },
    },
    overrides: [],
  },
  $data: queryRunner,
});
```

## Table panel patterns

Table panel options and field options live at different levels. Use `setOption` for panel-wide behavior and custom field config/overrides for columns:

```ts
import { PanelBuilders } from "@grafana/scenes";
import { TableCellDisplayMode, TableCellHeight } from "@grafana/schema";

const table = PanelBuilders.table()
  .setData(tableData)
  .setTitle("Services")
  .setOption("showHeader", true)
  .setOption("cellHeight", TableCellHeight.Sm)
  .setOption("enablePagination", true)
  .setOption("frozenColumns", { left: 1 })
  .setOption("sortBy", [{ displayName: "Request rate", desc: true }])
  .setCustomFieldConfig("align", "auto")
  .setCustomFieldConfig("minWidth", 90)
  .setCustomFieldConfig("cellOptions", { type: TableCellDisplayMode.Auto })
  .setOverrides((builder) =>
    builder
      .matchFieldsWithName("Request rate")
      .overrideUnit("reqps")
      .overrideDecimals(2)
      .overrideCustomFieldConfig("width", 160)
  )
  .build();
```

`enablePagination` and column filters change client-side display only; they do not reduce query cost. Multiple frames produce a dataset selector rather than one combined table.

For one sparkline per row, preserve the range query and add `timeSeriesTable` before the panel:

```ts
import { SceneDataTransformer } from "@grafana/scenes";

const tableRangeQuery = getRangeQuery();

const tableData = new SceneDataTransformer({
  $data: tableRangeQuery,
  transformations: [
    {
      id: "timeSeriesTable",
      options: { A: { stat: "lastNotNull" } },
    },
  ],
});

const sparklineTable = PanelBuilders.table()
  .setData(tableData)
  .setCustomFieldConfig("cellOptions", { type: TableCellDisplayMode.Auto })
  .setOverrides((builder) =>
    builder
      .matchFieldsWithName("Trend #A")
      .overrideDisplayName("Trend")
      .overrideUnit("reqps")
      .overrideCustomFieldConfig("cellOptions", {
        type: TableCellDisplayMode.Sparkline,
        hideValue: false,
      })
  )
  .build();
```

The transformation produces label columns and a frame-valued `Trend #A` column. Apply the sparkline cell type only to that trend field. Read [tables-and-sparklines.md](../dashboard/tables-and-sparklines.md) for the full data contract, JSON equivalents, threshold color, and performance guidance.

## Stat sparkline pattern

Give a stat panel the original range data and let the stat reduce it internally:

```ts
import { BigValueGraphMode } from "@grafana/schema";

const statRangeQuery = getRangeQuery();

const stat = PanelBuilders.stat()
  .setData(statRangeQuery)
  .setOption("reduceOptions", {
    values: false,
    calcs: ["lastNotNull"],
    fields: "",
  })
  .setOption("graphMode", BigValueGraphMode.Area)
  .setUnit("reqps")
  .build();
```

Do not insert a `reduce` transformation before this panel: it leaves only one point, so the stat value can render while the sparkline cannot. Stat sparklines also hide responsively when the tile is too small. `tableRangeQuery` and `statRangeQuery` must be distinct scene objects unless both panels inherit one provider from a common ancestor.

## Panel menu

```ts
import { VizPanelMenu } from "@grafana/scenes";

const menu = new VizPanelMenu({
  items: [
    {
      text: "Open in explore",
      onClick: () => locationService.push("/explore"),
    },
    { type: "divider" },
    { text: "Inspect", onClick: () => {/* ... */} },
  ],
});

PanelBuilders.timeseries()
  .setMenu(menu)
  .build();
```

For a dynamically-built menu:

```ts
const menu = new VizPanelMenu({});
menu.addActivationHandler(() => {
  menu.setState({
    items: computeMenuItems(menu.parent),
  });
});
```

## Header actions

Render arbitrary scene objects in the panel header (right side):

```ts
PanelBuilders.timeseries()
  .setHeaderActions([
    new SceneToolbarInput({ value: "", onChange: (v) => {} }),
  ])
  .build();
```

## Panel context — sharing state across panels

`PanelContext` (Grafana's panel-internal API) is plumbed through automatically. You usually don't need to touch it directly; `CursorSync` and other behaviors use it.

## Runtime panel plugins

Register a panel plugin only known to your scene (not visible to other plugins):

```ts
import { sceneUtils } from "@grafana/scenes";
import { MyPanel } from "./MyPanel";

sceneUtils.registerRuntimePanelPlugin({
  pluginId: "my-runtime-panel",
  plugin: new PanelPlugin(MyPanel)
    .setPanelOptions((b) => b.addTextInput({ path: "title", name: "Title" })),
});

// Then use:
PanelBuilders.custom("my-runtime-panel").setOption("title", "Hello").build();
```

This is powerful for app-specific visualizations that don't merit a full plugin.

## Subheader — adding content below the panel header

```ts
new VizPanel({
  pluginId: "timeseries",
  title: "Trend",
  subHeader: new SceneCanvasText({ text: "Last updated: now" }),
  // ...
});
```

`subHeader` accepts a React node, single scene object, or array of scene objects.

## VizPanelExploreButton

Show an "Explore" button that opens the queries in Grafana Explore:

```ts
import { VizPanelExploreButton } from "@grafana/scenes";

PanelBuilders.timeseries()
  .setHeaderActions([new VizPanelExploreButton({})])
  .build();
```

## Common gotchas

- **Panel doesn't render** — check `pluginId` is a real plugin name and not a typo. Also verify `$data` is set somewhere up the tree.
- **Options autocomplete missing** — make sure `PanelBuilders.<type>()` is the entry point, not `new VizPanel(...)`. The builders carry the options/fieldConfig types.
- **Field config not applying** — `defaults` apply to all fields; `overrides` apply only to matched fields. Verify your matcher.
- **Variables not interpolating in title/option strings** — they should auto-interpolate. If they don't, check the variable is in scope (ancestor `SceneVariableSet`).
- **Stat/gauge shows "No data"** — common when the query returns multiple series with no reduction. Use a `SceneDataTransformer` with `reduce` transformation, or set `options.reduceOptions.calcs = ['lastNotNull']`.
- **Table sparkline says "no data"** — a scalar or label field got the sparkline cell type. Run `timeSeriesTable` and override only its frame-valued `Trend #<refId>` field.
- **Stat shows a value but no sparkline** — confirm the panel receives a range field with at least two points, `reduceOptions.values` is false, `graphMode` is `area`, and the panel has enough height.
