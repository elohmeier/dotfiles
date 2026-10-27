# Variables

Variables parameterize scenes. They drive query templating, panel titles, layout repetition, and side effects. The system mirrors Grafana's dashboard template variables.

## SceneVariableSet — the container

Always wrap variables in a `SceneVariableSet`. Place it in `$variables` on the closest ancestor where you want variables in scope.

```ts
import { SceneVariableSet, QueryVariable, IntervalVariable, VariableValueSelectors } from '@grafana/scenes';

new EmbeddedScene({
  $variables: new SceneVariableSet({
    variables: [
      new QueryVariable({ name: 'cluster', ... }),
      new IntervalVariable({ name: 'interval', ... }),
    ],
  }),
  controls: [new VariableValueSelectors({})],
  body: ...,
});
```

`VariableValueSelectors` auto-renders all variables as Grafana-style dropdown / input controls. Place it in `controls`.

## Variable types

### `ConstantVariable` — fixed value

```ts
new ConstantVariable({
  name: "env",
  value: "production",
  skipUrlSync: true, // No need to expose in URL
});
```

### `CustomVariable` — comma-separated list

```ts
new CustomVariable({
  name: "region",
  label: "Region",
  query: "us-east, us-west, eu-west", // CSV format by default
  value: "us-east",
});

// Pretty labels with colon syntax:
new CustomVariable({
  name: "series",
  query: "Server Names : __server_names, House Locations : __house_locations",
  value: "__server_names",
});

// JSON format for complex values:
new CustomVariable({
  name: "config",
  valuesFormat: "json",
  query:
    "[{\"text\":\"A\",\"value\":\"alpha\"},{\"text\":\"B\",\"value\":\"beta\"}]",
});
```

### `QueryVariable` — datasource-driven

```ts
new QueryVariable({
  name: "job",
  label: "Job",
  datasource: { type: "prometheus", uid: "prom-uid" },
  query: { query: "label_values(up, job)" }, // Datasource-specific
  refresh: VariableRefresh.onTimeRangeChanged,
  sort: VariableSort.alphabeticalAsc,
  includeAll: true,
  isMulti: true,
});
```

`refresh` controls when the variable re-fetches:

- `VariableRefresh.never` — manual only
- `VariableRefresh.onDashboardLoad` — once on activation
- `VariableRefresh.onTimeRangeChanged` — every time range change

### `DataSourceVariable` — pick a datasource of a given type

```ts
new DataSourceVariable({
  name: "datasource",
  pluginId: "prometheus",
  regex: "prod-.*", // Filter by name
});
```

Use as `${datasource}` in query runners' `datasource` ref:

```ts
new SceneQueryRunner({
  datasource: { uid: '${datasource}' },
  queries: [...],
});
```

### `TextBoxVariable` — free text

```ts
new TextBoxVariable({
  name: "search",
  value: "",
  label: "Search",
});
```

### `IntervalVariable` — interval picker

```ts
new IntervalVariable({
  name: "interval",
  intervals: ["30s", "1m", "5m", "10m", "30m", "1h", "6h", "1d"],
  value: "1m",
  autoEnabled: true,
  autoMinInterval: "10s",
  autoStepCount: 30,
});
```

When `autoEnabled` is true, value `'$__auto'` resolves at query time based on time range and panel width.

### `AdHocFiltersVariable` — dynamic filters

User adds key/value/operator triplets at runtime, applied as label matchers on supported datasources.

```ts
import { AdHocFiltersVariable } from "@grafana/scenes";

new AdHocFiltersVariable({
  name: "filters",
  datasource: { type: "prometheus", uid: "prom" },
  filters: [],
  defaultFilters: [{ key: "env", operator: "=", value: "prod" }],
  addFilterButtonText: "Add filter",
});
```

Prometheus / Loki / others auto-apply ad-hoc filters to queries. To use them in your own data path:

```ts
import { sceneUtils } from "@grafana/scenes";
const labelString = sceneUtils.renderPrometheusLabelFilters(filters); // {env="prod",region="us-east"}
```

### `GroupByVariable` — group-by dimension picker

```ts
new GroupByVariable({
  name: "group_by",
  datasource: { type: "prometheus", uid: "prom" },
  defaultOptions: [],
  baseFilters: [{ key: "job", operator: "=", value: "api" }],
});
```

## Multi-value variables

`QueryVariable`, `CustomVariable`, `DataSourceVariable`, `GroupByVariable` extend `MultiValueVariable`. Add `isMulti: true` and `includeAll: true` to allow multiple selections and an "All" entry:

```ts
new QueryVariable({
  name: 'cluster',
  isMulti: true,
  includeAll: true,
  allValue: '.*',  // Sent as the value when "All" is selected (regex for Prometheus)
  ...
});
```

Use multi-value in queries with format suffixes:

```
${cluster:csv}    →  us-east,us-west
${cluster:pipe}   →  us-east|us-west
${cluster:json}   →  ["us-east","us-west"]
${cluster:regex}  →  (us\-east|us\-west)
```

## Interpolation formats

```
${var}              raw value (or csv if multi)
${var:raw}          raw, no escaping
${var:csv}          comma-separated for multi
${var:pipe}         pipe-separated
${var:regex}        regex-escaped
${var:json}         JSON-encoded
${var:doublequote}  "value"
${var:singlequote}  'value'
${var:lucene}       Lucene-escaped (Elasticsearch)
${var:percentencode} URL-encoded
${var:queryparam}   var-name=value form
${var:html}         HTML-escaped
${var:text}         Display label (not value)
${var:value}        Just the value
```

Apply manually with `sceneGraph.interpolate`:

```ts
import { sceneGraph } from "@grafana/scenes";

const url = sceneGraph.interpolate(this, "/api/data?cluster=${cluster:csv}");
```

## Built-in macros

### Global

```
${__url}                       Full current URL
${__url.path}                  Path without query
${__url.params}                Full query string
${__url.params:exclude:var-x}  Query string minus var-x
${__url.params:include:var-x,var-y}  Only those keys
${__from}                      Time range from (ms)
${__to}                        Time range to (ms)
${__interval}                  Calculated interval
${__interval_ms}               Interval in ms
${__timezone}
${__user.login}                Current user login
${__user.email}
${__org.name}
${__org.id}
```

### Field/series (in field configs, data links)

```
${__field.name}                Field/series name
${__field.labels.<label>}      Specific label
```

### Value/row (in data links, table cell links)

```
${__value.text}                Formatted value
${__value.raw}                 Unformatted value
${__data.fields[0].text}       First column on the same row
```

Useful for table-row drilldown links:

```ts
PanelBuilders.table()
  .setOverrides((b) =>
    b.matchFieldsWithName("roomName").overrideLinks([
      {
        title: "Open",
        url:
          `/a/${PLUGIN_ID}/page-with-drilldown/room/\${__value.raw}\${__url.params}`,
      },
    ])
  )
  .build();
```

## Variable change side effects

Use the `ActWhenVariableChanged` behavior:

```ts
import { behaviors } from '@grafana/scenes';

new EmbeddedScene({
  $variables: ...,
  $behaviors: [
    new behaviors.ActWhenVariableChanged({
      variableName: 'cluster',
      onChange: (variable) => {
        console.log('cluster changed:', variable.getValue());
        // Optionally return cleanup
      },
    }),
  ],
  body: ...,
});
```

## Custom macros

Register a runtime macro:

```ts
import { sceneUtils } from "@grafana/scenes";

sceneUtils.registerVariableMacro("myMacro", (match, scopedVars) => {
  return "computed-value";
});
// Usage: ${__myMacro}
```

## Programmatic access

```ts
const variables = sceneGraph.getVariables(this);
const v = variables.getByName("cluster");
const value = v.getValue(); // The current value
const valueText = v.getValueText?.(); // The display label (multi-val)
v.changeValueTo(["us-east", "us-west"]); // Programmatic update (MultiValueVariable)
```

## URL sync

By default, multi-value and text-box variables sync to URL as `?var-<name>=<value>`. Set `skipUrlSync: true` to opt out (e.g., constants).

`AdHocFiltersVariable` and `GroupByVariable` use their own URL serialization.

## Common pitfalls

- **`label_values(up,job)` returns nothing** — verify the datasource is reachable, the metric exists, and the time range is sensible. Variables with `refresh: onTimeRangeChanged` may have empty results outside their data window.
- **Multi-value not working in expr** — use `${var:regex}` for Prometheus label matchers, not just `${var}`.
- **Variable not in scope** — the `SceneQueryRunner` must be a descendant of the `SceneVariableSet`. If you put `$variables` on a child, queries above don't see it.
- **`changeValueTo()` doesn't update URL** — make sure URL sync is enabled at the SceneApp level. URL sync runs at scene-app level.
