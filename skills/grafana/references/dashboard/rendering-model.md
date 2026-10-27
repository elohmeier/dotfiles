# Grafana Panel Rendering Model

Use this when explaining how a Grafana panel is rendered or when dashboard JSON changes need to respect Grafana internals.

## Source Anchors

- Grafana panel state: `public/app/features/dashboard/state/PanelModel.ts`
- Dashboard panel wrapper: `public/app/features/dashboard/dashgrid/PanelStateWrapper.tsx`
- Panel chrome/header/status wrapper: `packages/grafana-ui/src/components/PanelChrome/PanelChrome.tsx`
- Chrome prop mapping: `public/app/features/dashboard/utils/getPanelChromeProps.tsx`
- Query runner: `public/app/features/query/state/PanelQueryRunner.ts`
- Panel plugin class: `packages/grafana-data/src/panel/PanelPlugin.ts`
- Transform pipeline: `packages/grafana-data/src/transformations/transformDataFrame.ts`
- Standard transformer registry: `packages/grafana-data/src/transformations/standardTransformersRegistry.ts`

## Runtime Flow

1. A persisted panel JSON is restored into `PanelModel`.
   - Defaults include `gridPos`, `targets`, `options`, `links`, `transformations`, and `fieldConfig`.
   - Missing query `refId`s are assigned.
   - Legacy/Angular panel types may be migrated, for example `graph` to `timeseries`, `singlestat` to `stat`, `table-old` to `table`, worldmap to `geomap`.
2. The panel plugin is loaded.
   - `PanelPlugin` owns the React panel component, default panel options, field config defaults, custom field config registry, migration handler, and panel type change handler.
   - `applyPluginOptionDefaults` merges plugin defaults into persisted `options` and `fieldConfig`.
3. `PanelStateWrapper` subscribes to `panel.getQueryRunner().getData({ withTransforms: true, withFieldConfig: true })`.
4. Refresh runs `panel.runAllPanelQueries`.
   - Request includes datasource, targets, panel id/title/type, dashboard uid/title, timezone, time range, max datapoints, min interval, scoped vars, cache settings, transformations, and app context.
5. `PanelQueryRunner` emits `PanelData`.
   - Raw query frames are optionally transformed.
   - Field overrides are applied after transformations.
   - `structureRev` increments when frame structure changes, helping visualizations rerender correctly.
6. `PanelStateWrapper` passes processed `PanelData` and panel props into the plugin component.
   - Props include `data`, `timeRange`, `timeZone`, `options`, `fieldConfig`, `width`, `height`, `replaceVariables`, event bus, and update callbacks.
7. `PanelChrome` wraps the plugin output.
   - It controls title, menu, drag/select behavior, loading indicator, status/error message, padding, transparent mode, hover header, and panel description/links.

## Important Consequences

- Transformations happen before field overrides. If a field is renamed or joined by a transformation, overrides should match the final field names.
- `updateFieldConfig` resends the last query result, so display changes do not need to rerun the datasource query.
- `updateOptions` rerenders the panel but generally does not rerun queries.
- Query and transformation changes affect the data stream and should be checked with Inspect/Data or transformation debug.
- Panels with `plugin.meta.skipDataQuery` render without datasource execution, for example text-like or static panels.
- Snapshot panels read `snapshotData` instead of rerunning queries.
- No-padding panels set `PanelChrome` padding to `none`; many visual panels use default padding.

## Rendering Debug Checklist

- Does the panel have data? Check `PanelData.state`, errors, and `series`.
- Does the visualization require a time field, numeric field, rows, buckets, trace frames, logs, or geospatial fields?
- Did transformations remove or rename a field needed by the panel?
- Are field overrides matching the final field display name, regex, type, query refId, or value condition?
- Is the query returning instant data where a time series panel expects range data?
- Is a title missing intentionally? Panels without titles may use overlay headers unless time override info is shown.
- Are table interactions persisting options/overrides, such as sorting or column width?
