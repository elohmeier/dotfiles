# Data and queries — SceneQueryRunner, transformers, data layers

Data flows through the scene graph via the `$data` slot. Any descendant object that needs data finds the closest ancestor's `$data`.

## SceneQueryRunner — the workhorse

```ts
import { SceneQueryRunner } from "@grafana/scenes";

const queryRunner = new SceneQueryRunner({
  datasource: {
    type: "prometheus",
    uid: "gdev-prometheus",
  },
  queries: [
    {
      refId: "A",
      expr: "rate(http_requests_total[5m])",
      legendFormat: "{{job}}",
    },
  ],
  minInterval: "1m",
  maxDataPoints: 3000,
});
```

State fields:

```ts
interface QueryRunnerState extends SceneObjectState {
  data?: PanelData; // Result with { series, state, timeRange, errors }
  queries: SceneDataQuery[];
  datasource?: DataSourceRef; // { type, uid }
  minInterval?: string; // e.g. '1m' — query step floor
  maxDataPoints?: number;
  liveStreaming?: boolean;
  maxDataPointsFromWidth?: boolean; // Compute MDP from panel width
  cacheTimeout?: string;
  queryCachingTTL?: string;
  runQueriesMode?: "auto" | "manual"; // 'manual' requires explicit runQueries() call
  dataLayerFilter?: DataLayerFilter; // Filter annotations/alerts
  requestIdPrefix?: string;
}
```

Methods:

```ts
queryRunner.runQueries(); // Manually re-run (e.g., after state change)
queryRunner.cancelQuery();
```

## Connecting queries to time and variables

`SceneQueryRunner` automatically:

- Re-runs when the closest ancestor `$timeRange` changes.
- Re-runs when any variable used in queries changes (interpolation tracked).
- Cancels in-flight queries when superseded.

You don't subscribe manually. Just put the query runner in `$data` and the scene graph wires it up.

```ts
new EmbeddedScene({
  $timeRange: new SceneTimeRange({ from: 'now-6h', to: 'now' }),
  $variables: new SceneVariableSet({
    variables: [new QueryVariable({ name: 'job', ... })],
  }),
  $data: new SceneQueryRunner({
    datasource: { type: 'prometheus', uid: '...' },
    queries: [{ refId: 'A', expr: 'rate(http_requests_total{job="$job"}[5m])' }],
  }),
  body: new SceneFlexLayout({ children: [
    new SceneFlexItem({ body: PanelBuilders.timeseries().build() }),
  ]}),
});
```

Variable interpolation in `expr`: use `$varname` or `${varname:format}` (formats: `csv`, `pipe`, `regex`, `json`, etc. — see references/scenes/05-variables.md).

## Per-panel data overrides

Putting `$data` on a child overrides the inherited data for that subtree:

```ts
new SceneFlexLayout({ children: [
  new SceneFlexItem({
    body: PanelBuilders.timeseries()
      .setTitle('Panel A — uses scene data')
      .build(),
  }),
  new SceneFlexItem({
    body: PanelBuilders.timeseries()
      .setTitle('Panel B — uses its own data')
      .setData(new SceneQueryRunner({ ... }))   // builder helper
      .build(),
  }),
]});
```

`PanelBuilders.<type>().setData(runner)` injects the runner into the panel's `$data`. Same as constructing a `VizPanel` with `$data`.

## SceneDataTransformer — pipeline transformations

Wrap a query runner (or any data provider) to apply Grafana transformations:

```ts
import { SceneDataTransformer } from "@grafana/scenes";

const data = new SceneDataTransformer({
  $data: queryRunner,
  transformations: [
    {
      id: "organize",
      options: { excludeByName: { Time: true } },
    },
    {
      id: "filterFieldsByName",
      options: { include: { names: ["value", "job"] } },
    },
  ],
});
```

Use the transformer where the query runner would go: `$data: data` on the scene or panel.

You can also write **custom inline transformations** with rxjs operators:

```ts
import { map } from "rxjs/operators";

new SceneDataTransformer({
  $data: queryRunner,
  transformations: [
    {
      id: "custom",
      options: {},
      // CustomTransformerDefinition: a function returning rxjs operator
      operator: () =>
        map((data) => ({
          ...data,
          series: data.series.map((s) => ({
            ...s,
            name: s.name?.toUpperCase(),
          })),
        })),
    },
  ],
});
```

## Static data — SceneDataNode

When you already have data (e.g., from a non-Grafana source or test fixture):

```ts
import { SceneDataNode } from '@grafana/scenes';
import { LoadingState } from '@grafana/data';

const staticData = new SceneDataNode({
  data: {
    series: [
      {
        refId: 'A',
        fields: [
          { name: 'time', values: [...] },
          { name: 'value', values: [...] },
        ],
        length: 100,
      },
    ],
    state: LoadingState.Done,
    timeRange: getDefaultTimeRange(),
  },
});
```

## Time range — SceneTimeRange

```ts
import { SceneTimeRange } from "@grafana/scenes";

const timeRange = new SceneTimeRange({
  from: "now-6h",
  to: "now",
  timeZone: "browser",
  refreshOnActivate: { afterMs: 60_000 }, // Refresh if mounted >60s ago
});
```

Methods:

```ts
timeRange.onTimeRangeChange({ from: ..., to: ..., raw: { ... } });
timeRange.onTimeZoneChange('UTC');
timeRange.onRefresh();   // Trigger a re-fetch downstream
```

The `SceneTimePicker` and `SceneRefreshPicker` controls call these for you when added to `EmbeddedScene.controls`.

## Data layers — annotations, alerts

Data layers add overlays to panels. Built-in: `AnnotationsDataLayer`, `AlertStatesDataLayer`.

```ts
import { dataLayers, SceneDataLayerSet, SceneDataLayerControls } from '@grafana/scenes';

const layers = new SceneDataLayerSet({
  layers: [
    new dataLayers.AnnotationsDataLayer({
      name: 'Deployments',
      query: {
        datasource: { type: 'prometheus', uid: 'prom' },
        enable: true,
        // ... annotation query
      },
    }),
  ],
});

new EmbeddedScene({
  $data: new SceneDataLayerSet({ layers: [...] }),
  controls: [new SceneDataLayerControls()],  // Toggle layers on/off
  body: ...,
});
```

To **combine** queries with data layers, set the query runner as `$data` on a panel (or sub-scene) and put data layers on the parent. Or compose via `SceneDataLayerSet`-aware transformers.

## Custom datasources at runtime

Register a scene-only runtime data source (not visible to other plugins) via `sceneUtils`:

```ts
import { sceneUtils } from "@grafana/scenes";

sceneUtils.registerRuntimeDataSource({
  dataSource: new MyRuntimeDataSource("my-runtime", "my-runtime-uid"),
});
```

`MyRuntimeDataSource` extends `RuntimeDataSource` (also from `@grafana/scenes`) with a `query(request)` method returning `Observable<DataQueryResponse>`. Useful when you want scene-driven data not backed by a real Grafana datasource (test data, computed values).

## Querying patterns

### Drive query state from a custom object

```ts
const queryRunner = new SceneQueryRunner({...});
const customObj = new MyControls({ count: 5 });

queryRunner.addActivationHandler(() => {
  const sub = customObj.subscribeToState((newState) => {
    queryRunner.setState({
      queries: [{ ...queryRunner.state.queries[0], seriesCount: newState.count }],
    });
    queryRunner.runQueries();
  });
  return () => sub.unsubscribe();
});
```

### React to time range without re-querying

```ts
new SceneQueryRunner({
  // refreshOnActivate prevents query but tracks time range
  $timeRange: new SceneTimeRange({ from: 'now-1h', to: 'now' }),
  ...
});
```

### Cancel queries when navigating away

Automatic — the query runner deactivates when its parent does.

## Common errors

- **`Datasource not found`** — `uid` in `datasource` doesn't exist. Provision it (`provisioning/datasources/`) or the user needs to add it.
- **Variable interpolation returns literal `$var`** — variable not in scope. Make sure the query runner is a descendant of the `SceneVariableSet`.
- **Query never runs** — usually missing `$timeRange`. Add `$timeRange: new SceneTimeRange()` somewhere up the tree.
- **Stale data after time change** — check that the time picker is in the same scene as the query runner (sharing the same `$timeRange`).
