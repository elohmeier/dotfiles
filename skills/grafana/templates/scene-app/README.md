# Scene-app template

Full multi-page `SceneApp` with home, hello-world, tabs, and drilldown pages.

## File map

```
plugin.json                              Manifest with 4 nav entries
constants.ts                             ROUTES enum, DATASOURCE_REF
components/App/App.tsx                   useSceneApp + SceneApp wiring
pages/
├── Home/
│   ├── homePage.ts                      SceneAppPage → homeScene
│   ├── homeScene.ts                     EmbeddedScene with var, query, custom obj
│   └── SeriesCountInput.tsx             Custom SceneObjectBase
├── HelloWorld/
│   ├── helloWorldPage.ts
│   └── helloWorldScene.ts
├── WithTabs/
│   └── withTabsPage.ts                  Two tabs reusing homeScene
└── WithDrilldown/
    ├── withDrilldownPage.ts             Parent + drilldown definition
    ├── withDrilldownScene.ts            Table with row data link
    └── roomDetailScene.ts               Per-room detail scene
```

## Pre-requisites in your project

This template assumes you've already scaffolded the rest of the plugin (the `plugin-skeleton/` template covers the bare bones). You need:

- `src/utils/utils.routing.ts` — `prefixRoute(route)`
- `src/utils/utils.plugin.ts` — `PluginPropsContext`
- `src/module.tsx` — `AppPlugin` entry
- `package.json` with `@grafana/scenes`, `@grafana/data`, `@grafana/runtime`, `@grafana/ui`

The easiest way to get those is `npx @grafana/create-plugin@latest` ➜ **App (with Scenes)**.

## Placeholders

- `${PLUGIN_ID}` — e.g., `myorg-monitoring-app`
- `${PLUGIN_NAME}` — display name
- `${ORG_NAME}` — author
- `${DATASOURCE_UID}` — uid of the datasource (e.g. `gdev-testdata` for the testdata DS)
- `${DATASOURCE_TYPE}` — datasource type (e.g. `testdata`)

## Wiring notes

- `App.tsx` calls `useSceneApp(getSceneApp)` with a module-scope factory. The factory identity is the cache key, so don't replace it with an inline callback.
- Tab parents use `routePath: '<base>/*'`. The trailing `/*` lets React Router descend into tab routes.
- The first tab uses `routePath: ''`; sibling tab paths are relative segments such as `locations`, never `/locations`.
- Page-level drilldowns use a relative pattern such as `room/:roomName/*`.
- `getParentPage: () => parent` on a drilldown wires up the breadcrumb back-link.
- The drilldown's data link uses `${__value.text:percentencode}${__url.params}` to encode the row value and preserve query state.
- Tabs appear as page navigation children. The tab container, not the active tab, supplies the breadcrumb item and page title.

## Going further

- Add variables that affect every page: put them on a top-level `SceneVariableSet` and pass it to `SceneApp` (every `SceneAppPage` inherits scope).
- `SceneAppPage` caches the scene returned by `getScene()` for each matched URL. Return a new scene for the first visit and never attach one scene instance to multiple parents.
- Add behaviors (cursor sync, auto-refresh): see `references/scenes/09-behaviors.md`.
