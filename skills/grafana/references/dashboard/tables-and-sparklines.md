# Tables and sparklines

Use this reference when building table panels, table sparkline cells, stat sparklines, or the equivalent panels in a Scenes app.

## Contents

- [Source anchors](#source-anchors)
- [Choose the right compact trend](#choose-the-right-compact-trend)
- [Table data and interaction model](#table-data-and-interaction-model)
- [Table sparkline data contract](#table-sparkline-data-contract)
- [Dashboard JSON patterns](#dashboard-json-patterns)
- [Stat sparkline behavior](#stat-sparkline-behavior)
- [Scenes patterns](#scenes-patterns)
- [Design and performance rules](#design-and-performance-rules)
- [Troubleshooting](#troubleshooting)

## Source anchors

Grafana source:

- Table panel: `public/app/plugins/panel/table/TablePanel.tsx`
- Table configuration: `public/app/plugins/panel/table/module.tsx` and `packages/grafana-schema/src/common/table.cue`
- Sparkline cell: `packages/grafana-ui/src/components/Table/Cells/SparklineCell.tsx`
- Time series to table: `public/app/features/transformers/timeSeriesTable/timeSeriesTableTransformer.ts`
- Stat panel: `public/app/plugins/panel/stat/StatPanel.tsx`
- Stat display values: `packages/grafana-data/src/field/fieldDisplay.ts`
- Stat responsive layout: `packages/grafana-ui/src/components/BigValue/BigValueLayout.tsx`
- Shared sparkline renderer: `packages/grafana-ui/src/components/Sparkline/utils.ts`

Documentation:

- Table: `docs/sources/visualizations/panels-visualizations/visualizations/table/index.md`
- Stat: `docs/sources/visualizations/panels-visualizations/visualizations/stat/index.md`
- Transformations: `docs/sources/visualizations/panels-visualizations/query-transform-data/transform-data/index.md`

## Choose the right compact trend

Use a stat sparkline when one reduced value is primary and its recent shape is supporting context. Use a table sparkline when users must compare the recent shape of several entities row by row. Use a full time series when exact timing, hover inspection, annotations, multiple series, or incident correlation is primary.

Do not use a sparkline as a miniature replacement for every time-series panel. Its axes and detail are intentionally suppressed.

## Table data and interaction model

A table renders one data frame at a time. If a query pipeline returns multiple frames, Grafana shows a dataset selector below the table and selects `options.frameIndex` for display. Merge or join frames when users need one coherent operational table; do not expect several frames to appear as adjacent columns automatically.

Keep the JSON ownership model straight:

| Concern                                                            | JSON location                                | Notes                                                                                              |
| ------------------------------------------------------------------ | -------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Header, row height, pagination, frozen columns, initial sort       | Panel `options`                              | Pagination changes visible rows, not query size.                                                   |
| Width, minimum width, alignment, filtering, wrapping, hidden state | `fieldConfig.defaults.custom` or an override | These settings belong to fields/columns.                                                           |
| Cell type                                                          | `custom.cellOptions`                         | Prefer an override when only one column is a gauge, sparkline, JSON view, or action.               |
| Unit, decimals, mappings, thresholds, links                        | Standard field config or an override         | Target the final field name after transformations.                                                 |
| Footer calculations                                                | `custom.footer.reducers`                     | Current Grafana stores reducers per field. Older dashboards can contain migrated `options.footer`. |

Useful behaviors and their limits:

- `sortBy` uses the field's display name and supports an initial ascending or descending order. Users can multi-sort interactively with Ctrl/Cmd-click.
- `enablePagination` derives page size from panel height. It does not reduce datasource work or returned rows.
- `frozenColumns.left` freezes the leftmost fields, so finalize transformation order before setting it.
- `filterable` enables temporary client-side column filters. Query variables and datasource filters remain the right choice for persistent, shareable, or cost-reducing filters.
- `width` fixes a column width; `minWidth` controls auto-sizing. Reduce `minWidth` for narrow screens, but do not compress identifiers until they become ambiguous.
- Data links are the normal drilldown mechanism. Apply them to the identifier field, preserve time and variable state, and percent-encode path values.
- Multiple input frames produce a selector, not a combined table. Use `merge`, `joinByField`, or another intentional reshape when one table is required.

Choose cell types by meaning:

- Keep identifiers and ordinary text/numbers on `auto` unless another presentation improves a concrete task.
- Use colored text/background for mapped states or thresholds. Apply row background only when the whole row shares that meaning.
- Use gauges for bounded scalar comparison; set meaningful min/max instead of accepting a misleading observed range.
- Use data links on the field that names the destination. Use the data-links cell type only when link titles are more useful than the original value.
- Use JSON view for inspectable structured data, pills for short bounded categories, and image only for trusted image URLs/data.
- Markdown/HTML, style-from-field, and actions expand the table's capability and risk. Keep content sanitized, avoid untrusted CSS/HTML, and remember table actions are basic unauthenticated requests.

Use tooltip-from-field when a hidden metadata field explains a visible value without adding another wide column. The tooltip source remains a real field and can receive mappings/formatting. Use `styleField` only for a controlled field containing JSON CSS properties; do not make arbitrary datasource content a styling channel.

For expandable sub-tables, use the Group to nested tables transformation. Parent-field overrides do not automatically target nested fields in current Grafana; select the nested target scope when configuring nested units, thresholds, links, or cell types.

## Table sparkline data contract

A table sparkline cell does not draw a line from an ordinary scalar column. Its cell value must be either:

- an array of numbers; or
- a nested data frame containing a time field and a numeric field.

For dashboard queries, use the `timeSeriesTable` transformation. For every query `refId`, it produces one table frame with:

- one row per numeric series;
- one column per series label; and
- a frame-valued field named `Trend #<refId>`.

Each `Trend #<refId>` cell contains the original time and numeric fields plus a scalar `value`. The scalar defaults to `lastNotNull`, is displayed next to the sparkline unless `hideValue` is true, and is also used when sorting that column. Configure a different reducer with `options.<refId>.stat`.

This ordering is essential:

```text
range query -> timeSeriesTable -> optional merge/join/organize -> field overrides -> table renderer
```

Apply `cellOptions.type: "sparkline"` only to `Trend #A` (or its renamed final field). If defaults set every field to sparkline, label columns cannot satisfy the nested-frame contract and render `no data`.

The shared sparkline renderer needs at least two values. Keep the query as a range query, and set `maxDataPoints` high enough to show shape but low enough to bound work across all rows. About 30-100 points per row is usually enough for a small cell; validate with the actual panel width and time range.

When multiple refIds are transformed, the transformer returns one table frame per refId. Join or merge them on stable label fields if the user needs multiple trend columns in a single row.

## Dashboard JSON patterns

### Classic dashboard JSON

```json
{
  "type": "table",
  "targets": [
    {
      "refId": "A",
      "expr": "sum by (service) (rate(http_requests_total[$__rate_interval]))",
      "format": "time_series",
      "instant": false
    }
  ],
  "transformations": [
    {
      "id": "timeSeriesTable",
      "options": {
        "A": { "stat": "lastNotNull" }
      }
    }
  ],
  "options": {
    "showHeader": true,
    "cellHeight": "sm",
    "enablePagination": true,
    "sortBy": [{ "displayName": "Trend", "desc": true }]
  },
  "fieldConfig": {
    "defaults": {
      "custom": {
        "align": "auto",
        "cellOptions": { "type": "auto" },
        "inspect": false
      }
    },
    "overrides": [
      {
        "matcher": { "id": "byName", "options": "Trend #A" },
        "properties": [
          { "id": "displayName", "value": "Trend" },
          { "id": "unit", "value": "reqps" },
          {
            "id": "custom.cellOptions",
            "value": {
              "type": "sparkline",
              "drawStyle": "line",
              "lineInterpolation": "smooth",
              "lineWidth": 1,
              "fillOpacity": 17,
              "showPoints": "never",
              "hideValue": false
            }
          }
        ]
      }
    ]
  }
}
```

### Dashboard schema v2

In `dashboard.grafana.app/v2`, the same transformation uses a kind/group wrapper:

```json
{
  "kind": "Transformation",
  "group": "timeSeriesTable",
  "spec": {
    "options": {
      "A": { "stat": "lastNotNull" }
    }
  }
}
```

The table visualization remains `vizConfig.group: "table"`. Field defaults and overrides remain under `vizConfig.spec.fieldConfig`. See `assets/dashboard/table-sparklines-v2.json` for a complete schema-v2 dashboard containing both table and stat sparklines.

### Threshold color

For a table sparkline colored by thresholds, apply both the threshold color mode and thresholds to the trend field override:

```json
{
  "id": "color",
  "value": { "mode": "thresholds" }
}
```

The sparkline cell selects the scheme gradient when threshold coloring is active. Thresholds should encode an operational boundary, not merely divide the observed range into decorative colors.

## Stat sparkline behavior

Set `options.graphMode` to `"area"` to request a stat sparkline. The stat panel:

1. reduces each selected numeric field with `reduceOptions.calcs`;
2. displays that reduced value; and
3. attaches the original numeric field and its time field as sparkline data.

Important consequences:

- Keep `reduceOptions.values` false. The all-values branch renders individual rows and does not attach a sparkline.
- Do not put a `reduce` transformation before a stat that needs a sparkline. That collapses the historical field to one point.
- Use a range query with a time field and at least two points. An instant query can show a stat value but cannot show a useful trend.
- The sparkline shows the raw field history while the large number shows the configured reducer. A `mean` value over an area sparkline is valid only when that pairing answers the user's question.
- Stat sparklines expose only `none` and `area`; their line and fill styling is intentionally constrained. Use a table sparkline or time-series panel when line, bar, point, interpolation, or null styling matters.
- Responsive layout hides the graph when there is too little space. In current Grafana code, wide layouts need more than 50 px of height and stacked layouts need more than 100 px, and both need at least two points. Treat this as responsive behavior, not a data failure.
- The sparkline color follows the stat's display color. With threshold colors, the current reduced value can color the entire compact trend; it is not a per-point threshold history.

Minimal stat options:

```json
{
  "reduceOptions": {
    "values": false,
    "calcs": ["lastNotNull"],
    "fields": ""
  },
  "textMode": "auto",
  "colorMode": "value",
  "graphMode": "area"
}
```

## Scenes patterns

Build the table transformation as a data provider and override only the generated trend field:

```ts
import {
  PanelBuilders,
  SceneDataTransformer,
  SceneQueryRunner,
} from "@grafana/scenes";
import { TableCellDisplayMode } from "@grafana/schema";

function getRangeQuery() {
  return new SceneQueryRunner({
    datasource: DATASOURCE_REF,
    queries: [
      {
        refId: "A",
        expr: "sum by (service) (rate(http_requests_total[$__rate_interval]))",
        range: true,
        format: "time_series",
      },
    ],
    maxDataPoints: 60,
  });
}

const tableQuery = getRangeQuery();

const tableData = new SceneDataTransformer({
  $data: tableQuery,
  transformations: [
    {
      id: "timeSeriesTable",
      options: { A: { stat: "lastNotNull" } },
    },
  ],
});

const table = PanelBuilders.table()
  .setData(tableData)
  .setOption("showHeader", true)
  .setOption("sortBy", [{ displayName: "Trend", desc: true }])
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

For a stat, give the panel the untransformed range data:

```ts
import { BigValueGraphMode } from "@grafana/schema";

const statQuery = getRangeQuery();

const stat = PanelBuilders.stat()
  .setData(statQuery)
  .setOption("reduceOptions", {
    values: false,
    calcs: ["lastNotNull"],
    fields: "",
  })
  .setOption("graphMode", BigValueGraphMode.Area)
  .setUnit("reqps")
  .build();
```

Do not attach the same query runner to both the transformer and the stat: scene objects cannot have two parents. Use separate runners as above, or place one shared provider on a common ancestor and let both panels inherit it. The table needs a child transformation that creates nested frame values, while the stat needs the original numeric range field.

## Design and performance rules

- Put stable identity columns first, then current value/status, then compact trend, then secondary metadata and actions.
- Freeze only identity/action columns that users must retain while scrolling horizontally.
- Use one obvious primary data link per row. Keep destructive or unauthenticated actions out of monitoring tables unless the workflow and permissions are explicit.
- Set units and decimals on numeric and trend fields. The scalar beside a sparkline uses the same display processor.
- Use no-value text that distinguishes no matching series from a valid zero. A broken trend with a plausible last value can otherwise look healthy.
- Bound rows at the query and bound points with `maxDataPoints`. Pagination and client filters do not reduce query or transformation cost.
- Test light and dark themes, narrow widths, long identifiers, null gaps, one-point series, out-of-order time, many rows, and multiple frames.
- Use browser validation for keyboard navigation, sorting, filtering, links, tooltips, frozen columns, and responsive sparkline visibility. Visible-data checks validate values and field configuration but do not render canvas/SVG output.

## Troubleshooting

| Symptom                                                | Likely cause                                                                  | Check                                                                               |
| ------------------------------------------------------ | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Sparkline cell says `no data`                          | Scalar/string field received the sparkline cell type                          | Inspect the frame and target `Trend #A`, a frame field, with the override.          |
| Every label column says `no data`                      | Sparkline was set in field defaults                                           | Restore defaults to `auto`; override only the trend field.                          |
| One row per query instead of one row per series        | Query output or labels were reduced before `timeSeriesTable`                  | Inspect data before the transform and keep the range series separated.              |
| Multiple dataset selector entries                      | More than one refId/frame remains                                             | Merge or join on stable label fields, or intentionally choose `frameIndex`.         |
| Sparkline sorts strangely                              | The configured transform reducer does not match the displayed question        | Set `options.<refId>.stat` and verify the nested frame's scalar value.              |
| Stat value works but no graph appears                  | Instant/reduced data, one point, `values: true`, or a panel that is too small | Inspect raw range data and panel dimensions.                                        |
| Threshold-colored stat graph looks uniformly red/green | Stat uses the reduced value's display color for the compact graph             | Use a full time series or table sparkline if historical threshold crossings matter. |
