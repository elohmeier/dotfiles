# @grafana/scenes-react — the hooks API

`@grafana/scenes-react` is an alternative API on top of `@grafana/scenes` that uses React patterns: context providers, hooks, and JSX components. It's lower-level and lighter than the imperative scene-object API, and good when:

- You're already in a React-heavy codebase and don't want a parallel object model.
- Your app is simple — a couple of pages, a few panels, a variable or two.
- You want to gradually adopt scenes inside an existing React app.

It's a **work in progress** package — feature parity with `@grafana/scenes` is not complete. For full SceneApp routing with tabs/drilldowns, prefer the imperative API.

## Mental model

| `@grafana/scenes`            | `@grafana/scenes-react`                            |
| ---------------------------- | -------------------------------------------------- |
| `EmbeddedScene`              | `<SceneContextProvider>`                           |
| `SceneTimeRange` constructor | `timeRange` prop on provider                       |
| `SceneVariableSet`           | `<CustomVariable>`, `<QueryVariable>` JSX wrappers |
| `SceneQueryRunner`           | `useQueryRunner()`                                 |
| `SceneDataTransformer`       | `useDataTransformer()`                             |
| `VizPanel` (scene object)    | `<VizPanel>` (component)                           |
| `SceneTimePicker`            | `<TimeRangePicker>`                                |
| `VariableValueSelectors`     | `<VariableControl>`                                |
| `SceneFlexLayout`, etc.      | `<SceneFlexLayout>`, `<VizGridLayout>`             |

## Setup

```bash
yarn add @grafana/scenes @grafana/scenes-react
```

Wrap your top-level component:

```tsx
import {
  CustomVariable,
  RefreshPicker,
  SceneContextProvider,
  TimeRangePicker,
  useQueryRunner,
  VariableControl,
  VizGridLayout,
  VizPanel,
} from "@grafana/scenes-react";

export function MyApp() {
  return (
    <SceneContextProvider
      timeRange={{ from: "now-1h", to: "now" }}
      withQueryController
    >
      <CustomVariable name="env" query="dev, test, prod" initialValue="dev">
        <Toolbar />
        <Body />
      </CustomVariable>
    </SceneContextProvider>
  );
}

function Toolbar() {
  return (
    <Stack direction="row" gap={1}>
      <VariableControl name="env" />
      <Spacer />
      <TimeRangePicker />
      <RefreshPicker />
    </Stack>
  );
}

function Body() {
  const data = useQueryRunner({
    queries: [{ refId: "A", expr: "up{env=\"$env\"}" }],
    datasource: { type: "prometheus", uid: "prom" },
  });

  return (
    <VizGridLayout>
      <VizPanel title="Up" viz="timeseries" dataProvider={data} />
    </VizGridLayout>
  );
}
```

## SceneContextProvider

The root context. Provides time range, query controller, variables.

```tsx
<SceneContextProvider
  timeRange={{ from: "now-6h", to: "now" }}
  withQueryController // Adds query controller for cancel/track
>
  {children}
</SceneContextProvider>;
```

Nest providers to override sub-tree time range or to scope variables.

## Variables

Each variable type has a JSX wrapper that registers it in the surrounding context:

```tsx
<CustomVariable name="region" query="us, eu" initialValue="us">
  <QueryVariable
    name="cluster"
    datasource={{ type: "prometheus", uid: "prom" }}
    query="label_values(cluster)"
  >
    <RestOfApp />
  </QueryVariable>
</CustomVariable>;
```

Available wrappers (`@grafana/scenes-react/src/variables/`):

- `<CustomVariable>`
- `<QueryVariable>`
- `<DataSourceVariable>`
- `<AdHocFiltersVariable>`
- `<GroupByVariable>`
- `<LocalValueVariable>` — scene-react-only; useful for lightweight local state participating in interpolation

### Reading variable values

```tsx
import { useVariableValue, useVariableValues } from "@grafana/scenes-react";

function Filter() {
  const [value, isLoading] = useVariableValue("region");
  // ...
}

function MultiFilter() {
  const [values, valueText, isLoading] = useVariableValues("cluster");
  // ...
}
```

### Programmatic mutation

```tsx
const { changeValueTo } = useQueryVariable("cluster");
changeValueTo(["prod-us", "prod-eu"]);
```

## Queries

```tsx
const data = useQueryRunner({
  queries: [{ refId: "A", expr: "up" }],
  datasource: { type: "prometheus", uid: "prom" },
  maxDataPoints: 1000,
});
```

`data` is a stable `SceneDataProvider` you can pass to `<VizPanel>` or further `useDataTransformer`.

```tsx
const transformed = useDataTransformer({
  data,
  transformations: [{ id: 'organize', options: { ... } }],
});
```

## Visualizations

```tsx
<VizPanel
  title="Latency"
  viz="timeseries"
  dataProvider={data}
  options={{ legend: { displayMode: "list" } }}
  fieldConfig={{ defaults: { unit: "s" }, overrides: [] }}
  hoverHeader={true}
/>;
```

`viz` is the panel plugin id (`'timeseries'`, `'stat'`, etc.).

## Layouts

```tsx
<VizGridLayout>
  <VizPanel title="A" viz="stat" dataProvider={dataA} />
  <VizPanel title="B" viz="stat" dataProvider={dataB} />
</VizGridLayout>

// Or flex:
<SceneFlexLayout direction="column">
  <SceneFlexItem minHeight={200}>
    <VizPanel title="Top" viz="timeseries" dataProvider={dataA} />
  </SceneFlexItem>
  <SceneFlexItem ySizing="fill">
    <VizPanel title="Bottom" viz="table" dataProvider={dataB} />
  </SceneFlexItem>
</SceneFlexLayout>
```

## Annotations

```tsx
import { AnnotationLayer } from "@grafana/scenes-react";

<AnnotationLayer
  name="Deployments"
  query={{
    datasource: { type: "prometheus", uid: "prom" },
    enable: true,
    iconColor: "red",
    expr: "changes(up{job=\"deployer\"}[1m])",
  }}
>
  <Body />
</AnnotationLayer>;
```

## Routing

`@grafana/scenes-react` doesn't ship a `SceneApp`-equivalent. Use plain `react-router-dom`:

```tsx
import { Route, Routes } from "react-router-dom";

export function MyApp() {
  return (
    <SceneContextProvider
      timeRange={{ from: "now-1h", to: "now" }}
      withQueryController
    >
      <Routes>
        <Route path="" element={<HomePage />} />
        <Route path="/details/:id" element={<DetailsPage />} />
      </Routes>
    </SceneContextProvider>
  );
}
```

For breadcrumbs, use the included `BreadcrumbProvider` and `<Breadcrumb>`:

```tsx
import { Breadcrumb, BreadcrumbProvider } from "@grafana/scenes-react";

<BreadcrumbProvider>
  <Breadcrumb text="Home" path="/" />
  <Routes>
    <Route
      path="/details/:id"
      element={
        <>
          <Breadcrumb text="Details" path="/details/:id" />
          <DetailsPage />
        </>
      }
    />
  </Routes>
</BreadcrumbProvider>;
```

## Interop with imperative scenes

`<EmbeddedSceneWithContext>` wraps an imperative `EmbeddedScene` so it picks up the surrounding React context (variables, time range):

```tsx
import { EmbeddedSceneWithContext } from "@grafana/scenes-react";
import { someEmbeddedScene } from "./scene";

<EmbeddedSceneWithContext model={someEmbeddedScene} />;
```

Useful when you have existing imperative scenes you want to drop into a scenes-react app.

## Choosing between APIs

Prefer **imperative `@grafana/scenes`** when:

- You have multi-page navigation with tabs and drilldowns (`SceneApp`).
- You want full URL sync semantics.
- You're building custom scene objects that orchestrate complex state.
- You're following the `create-plugin` scenes-app template (which uses the imperative API).

Prefer **`@grafana/scenes-react`** when:

- You're integrating into an existing React-only codebase.
- You don't need `SceneApp`'s page abstraction.
- The team prefers hooks/components over class-based scene objects.

You can mix them: a `SceneApp` can render imperative scenes, and within an `EmbeddedScene`, you can drop a `SceneReactObject` containing components that use scenes-react hooks (with `EmbeddedSceneWithContext` boundaries if needed).
