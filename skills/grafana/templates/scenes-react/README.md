# scenes-react template

Same kind of app as `scene-app/`, but built with `@grafana/scenes-react` hooks.

## Files

```
App.tsx                          Root: SceneContextProvider + variables + Routes
pages/HomePage.tsx               useQueryRunner + <VizPanel>
pages/DetailsPage.tsx            Drilldown via react-router params
```

## Required dependencies

```json
{
  "dependencies": {
    "@grafana/scenes": "^6.x",
    "@grafana/scenes-react": "^x.x.x",
    "@grafana/data": "^12.4.x",
    "@grafana/runtime": "^12.4.x",
    "@grafana/ui": "^12.4.x",
    "react-router-dom": "^6.x"
  }
}
```

`@grafana/scenes-react` is in active development — version pinning matters more than for `@grafana/scenes`.

## When to use this over the imperative API

Pick the hooks API when:

- Your team is React-first and dislikes class-based scene objects.
- You don't need the full `SceneApp` page abstraction (tabs, drilldowns with breadcrumbs).
- You're embedding scenes inside an existing React app.

Stick with `@grafana/scenes` (the imperative API in `templates/scene-app/`) when:

- You need URL sync with breadcrumbs and named pages (`SceneApp` + `SceneAppPage`).
- You want feature parity with the official `create-plugin` template.
- You're building tabs and drilldowns.

You can mix the two: render an imperative `EmbeddedScene` inside a scenes-react app via `<EmbeddedSceneWithContext>`.

## Pitfalls

- **Variable not in scope** — make sure the `<VariableControl name="env" />` is rendered _inside_ the corresponding `<CustomVariable name="env">` provider.
- **`useQueryRunner` returns a stable provider** — pass it as `dataProvider`, don't mutate the query inline (use a state-driven approach if queries change).
- **Routing is your responsibility** — there's no `SceneApp` here. Use `react-router-dom` and `BreadcrumbProvider` from `@grafana/scenes-react` for breadcrumbs.
