# Grafana Panel Type Reference

Use this to choose panels and diagnose data-shape mismatches.

## Contents

- [Source anchors](#source-anchors)
- [Common panel choices](#common-panel-choices)
- [Cross-cutting options](#cross-cutting-options)

## Source Anchors

Panel docs live under `docs/sources/visualizations/panels-visualizations/visualizations/`.

Implementation anchors:

- Time series: `public/app/plugins/panel/timeseries/TimeSeriesPanel.tsx`
- Stat: `public/app/plugins/panel/stat/StatPanel.tsx`
- Table: `public/app/plugins/panel/table/TablePanel.tsx`
- Bar gauge: `public/app/plugins/panel/bargauge/BarGaugePanel.tsx`
- Gauge: `public/app/plugins/panel/gauge/GaugePanel.tsx`
- Heatmap: `public/app/plugins/panel/heatmap/HeatmapPanel.tsx`
- Histogram: `public/app/plugins/panel/histogram/HistogramPanel.tsx`
- State timeline: `public/app/plugins/panel/state-timeline/StateTimelinePanel.tsx`
- Status history: `public/app/plugins/panel/status-history/StatusHistoryPanel.tsx`
- Geomap: `public/app/plugins/panel/geomap/GeomapPanel.tsx`
- Canvas: `public/app/plugins/panel/canvas/CanvasPanel.tsx`
- Logs: `public/app/plugins/panel/logs/LogsPanel.tsx`
- Logs table: `public/app/plugins/panel/logstable/LogsTable.tsx`
- Traces: `public/app/plugins/panel/traces/TracesPanel.tsx`
- Node graph: `public/app/plugins/panel/nodeGraph/NodeGraphPanel.tsx`
- Pie chart: `public/app/plugins/panel/piechart/PieChartPanel.tsx`
- Text: `public/app/plugins/panel/text/TextPanel.tsx`
- Dashboard list: `public/app/plugins/panel/dashlist/DashList.tsx`

## Common Panel Choices

Time series:

- Use for numeric values over time.
- Requires a time field and at least one numeric field.
- Multiple numeric fields become multiple rendered series.
- Good for rates, latency percentiles, saturation trends, queue depth, and resource utilization.
- Common pitfalls: instant query data, long-format frames that need "Prepare time series", excessive label cardinality, too many series in legend.

Stat:

- Use for one or a small set of reduced values.
- Works with single values or time series reduced by calculation.
- Good for SLO burn, current error ratio, availability, current saturation, latest build age.
- Configure reduce options, text mode, color mode, sparkline, thresholds, and no-value text.
- A stat sparkline needs unreduced range data with at least two points, `reduceOptions.values: false`, and `graphMode: "area"`. It is hidden when the tile is too small.
- The displayed number is reduced while the graph uses the original field history. Do not reduce the frame upstream when a sparkline is required.

Gauge:

- Use for one value with a meaningful bounded range.
- Requires min/max or a domain that can be inferred.
- Good for utilization percent, quota consumed, health score.
- Avoid when there are many dimensions; use bar gauge or table.

Bar gauge:

- Use for comparing many reduced values across categories.
- Good for top services by error rate, node CPU percent, per-queue backlog.
- Keep categories bounded; sort or limit upstream.

Table:

- Use for row-level detail, mixed data types, exact values, links, and lists.
- Supports multiple datasets with a selector.
- Configure column width, alignment, filtering, pagination, footer calculations, data links/actions, and cell types.
- Use transformations or overrides to hide noisy columns, rename fields, order fields, and render gauges/sparklines/JSON/images.
- Multiple frames produce a dataset selector, not adjacent columns. Merge or join only when there is a stable key and one coherent table is the intended result.
- A sparkline cell needs an array or nested data frame, not a scalar. Use `timeSeriesTable`, then target only `Trend #<refId>` with the sparkline override.
- Read [tables-and-sparklines.md](tables-and-sparklines.md) for exact JSON, Scenes builders, table option ownership, and sparkline behavior.

State timeline:

- Use for categorical states over time, especially per entity lanes.
- Good for pod phase, deployment status, feature flag state, service health state.
- Use value mappings and thresholds carefully.

Status history:

- Use for compact status changes over time, often many rows.
- Good for uptime/down state, pass/fail, alert state history.

Heatmap:

- Use for distributions over time.
- Good for latency histograms and request duration distributions.
- Prometheus histograms often need heatmap format or histogram-bucket handling.

Histogram:

- Use for distribution of values, not necessarily over time.
- Good for size distribution, latency sample distribution, counts by bucket.

Pie chart:

- Use sparingly for part-to-whole at one point in time with few categories.
- Avoid for time-varying comparisons or many slices.

Bar chart:

- Use for categorical comparisons with one or more numeric fields.
- Better than pie for comparing category magnitudes.

XY chart:

- Use when x is not time, or when plotting relationship between numeric fields.
- Requires explicit x/y field mapping.

Trend:

- Use for compact trend display where a stat-like view needs historical context.

Logs and logs table:

- Use for log lines and extracted fields.
- Logs table is better when field selection, details, and structured log columns matter.
- Use derived fields/data links for trace IDs and runbook links.

Traces:

- Use for trace data, spans, and TraceQL-oriented workflows.
- Link from metrics and logs by trace ID where possible.

Node graph:

- Use for nodes/edges relationships with source/target fields.
- Good for service dependency graphs only when relationships are meaningful and bounded.

Geomap:

- Use for latitude/longitude, geohash, lookup-able location fields, or geospatial layers.
- Choose layer type based on data: markers, heatmap, route, GeoJSON, network, photos.

Canvas:

- Use for custom schematic or process views.
- Best for NOC screens or physical/logical diagrams where individual elements bind to fields.
- Keep it maintainable; avoid replacing normal charts with decorative layouts.

Text:

- Use for dashboard documentation, runbooks, explanations, and section headings.

Dashboard list:

- Use for a dashboard-of-dashboards or tagged/folder navigation.

Alert list, annotations, news:

- Use for contextual lists and operational awareness, not primary metric analysis.

## Cross-Cutting Options

- Standard options: unit, min, max, field min/max, decimals, display name, color scheme, no value.
- Thresholds: use absolute or percentage mode; colors should match operational meaning.
- Value mappings: map values, ranges, regex, or special values to text/color.
- Legend: visibility, mode, placement, width, limit, values, sorting.
- Tooltip: single/all/none, sort order, hide zeros, proximity, max width/height.
- Field overrides: match by name, regex, type, query, or value; use for per-series settings.
- Data links/actions: use time range, series, field, value, data, and template variables for drilldowns.
