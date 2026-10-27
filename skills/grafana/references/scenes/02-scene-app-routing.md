# SceneApp routing, tabs, drilldowns, and breadcrumbs

`SceneApp` routes top-level `SceneAppPage` objects. Each page owns an absolute navigation URL and a route pattern relative to the router that renders it. Most routing bugs come from confusing those two values or from assuming breadcrumbs follow URLs rather than the scene-page parent chain.

## Contents

- [Source anchors](#source-anchors)
- [Runtime model](#runtime-model)
- [Create one stable SceneApp](#create-one-stable-sceneapp)
- [URL and routePath](#url-and-routepath)
- [Simple page](#simple-page)
- [Tabs](#tabs)
- [Drilldowns](#drilldowns)
- [Breadcrumb model](#breadcrumb-model)
- [URL state preservation](#url-state-preservation)
- [Fallback routes](#fallback-routes)
- [Manifest navigation](#manifest-navigation)
- [Verification checklist](#verification-checklist)
- [Common failures](#common-failures)

## Source anchors

Inspect the version of `@grafana/scenes` pinned by the target Grafana/plugin. In the Scenes repository, the relevant files are:

- `packages/scenes/src/components/SceneApp/SceneApp.tsx`
- `packages/scenes/src/components/SceneApp/SceneAppPage.tsx`
- `packages/scenes/src/components/SceneApp/SceneAppPageView.tsx`
- `packages/scenes/src/components/SceneApp/utils.ts`
- `packages/scenes/src/components/SceneApp/types.ts`
- `packages/scenes/src/components/SceneApp/SceneApp.test.tsx`

The behavior below was verified against `@grafana/scenes` 8.13.0, the version pinned by the inspected Grafana checkout. Recheck these anchors when targeting a materially different version.

## Runtime model

```text
SceneApp
└── top-level SceneAppPage                 outer <Routes>
    ├── tabs: SceneAppPage[]               inner <Routes>, registered at container level
    ├── page drilldowns                    inner <Routes>, registered at container level
    └── tab drilldowns                     also registered at container level
        └── getPage(match, parent)          dynamic SceneAppPage, cached by matched URL
```

`SceneAppPage` caches both its embedded scenes and dynamic drilldown pages by matched URL. `getScene` is a factory for the first visit to a URL, not a function called on every React render.

## Create one stable SceneApp

Use a module-scope factory with `useSceneApp`:

```tsx
import { SceneApp, useSceneApp } from "@grafana/scenes";

function getSceneApp() {
  return new SceneApp({
    pages: [homePage, servicesPage],
    urlSyncOptions: {
      updateUrlOnInit: true,
      createBrowserHistorySteps: true,
    },
  });
}

export function AppWithScenes() {
  const app = useSceneApp(getSceneApp);
  return <app.Component model={app} />;
}
```

`useSceneApp` caches by factory-function identity for the lifetime of the browser tab. Do not pass an inline function because it has a new identity on every render:

```tsx
// Wrong: a new factory key can create a new app on each render.
const app = useSceneApp(() => new SceneApp({ pages }));
```

A stable `useMemo(() => new SceneApp(...), [])` is also valid, but `useSceneApp` with a module-scope factory matches the plugin template and preserves the app beyond component remounts.

Do not attach one scene object instance to multiple parents. A page factory should create a new `EmbeddedScene` for its page/URL cache entry; use `clone()` or `SceneObjectRef` when intentional sharing is required.

## URL and routePath

In current Scenes, both values are required:

- `url` is the absolute application URL used by links, tabs, and breadcrumb items, for example `/a/myorg-app/services/api`.
- `routePath` is the React Router pattern at the route level where the page is registered. Child paths are relative and do not start with `/`.

Use this matrix:

| Page role                                | `url`                                      | `routePath`                                                                 |
| ---------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------- |
| Top-level leaf                           | `/a/myorg-app/home`                        | `home`                                                                      |
| Top-level container with tabs/drilldowns | `/a/myorg-app/services`                    | `services/*`                                                                |
| First tab at the container URL           | `/a/myorg-app/services`                    | `""`                                                                        |
| Sibling tab                              | `/a/myorg-app/services/logs`               | `logs` or `logs/*` when it has children                                     |
| Page-level drilldown definition          | dynamic absolute URL is built in `getPage` | `service/:service/*`                                                        |
| Returned drilldown page                  | `/a/myorg-app/services/service/api`        | a required relative pattern, normally the same `service/:service/*` pattern |

Rules:

- Add `/*` to every page that must match deeper path segments.
- Never write child tab paths such as `"/logs"` or `"/"`. A leading slash changes them from relative child patterns and can break descendant routing.
- Keep route constants as segments without leading/trailing slashes. Let `prefixRoute` build the absolute URL.
- `url` and `routePath` describe the same destination from different coordinate systems; test them as a pair.

## Simple page

```ts
import { SceneAppPage } from "@grafana/scenes";
import { ROUTES } from "../../constants";
import { prefixRoute } from "../../utils/utils.routing";
import { homeScene } from "./homeScene";

export const homePage = new SceneAppPage({
  title: "Home",
  subTitle: "Operational overview",
  url: prefixRoute(ROUTES.Home),
  routePath: ROUTES.Home,
  getScene: () => homeScene(),
});
```

Use a wildcard route such as `` routePath: `${ROUTES.Home}/*` `` instead if this page will own tabs or drilldowns.

## Tabs

Tabs are child `SceneAppPage` objects, but the container page supplies the page title, subtitle, controls, and breadcrumb item. Tab titles render as navigation children under that page header.

```ts
export const servicesPage = new SceneAppPage({
  title: "Services",
  subTitle: "Current service health",
  url: prefixRoute(ROUTES.Services),
  routePath: `${ROUTES.Services}/*`,
  tabs: [
    new SceneAppPage({
      title: "Overview",
      url: prefixRoute(ROUTES.Services),
      routePath: "",
      preserveUrlKeys: ["from", "to", "timezone", "var-environment"],
      getScene: () => overviewScene(),
    }),
    new SceneAppPage({
      title: "Logs",
      url: prefixRoute(`${ROUTES.Services}/logs`),
      routePath: "logs",
      preserveUrlKeys: ["from", "to", "timezone", "var-environment"],
      getScene: () => logsScene(),
    }),
  ],
});
```

The renderer always registers the first tab at the empty default route. This makes the first tab render at the parent's bare URL even when its own `routePath` is another segment. Prefer `routePath: ""` when the first tab's canonical `url` is exactly the parent URL; use a non-empty path only when that tab also needs its own address.

Do not set `hideFromBreadcrumbs: true` merely because a page has tabs. It hides the container's page item; it does not convert tab labels into breadcrumbs.

## Drilldowns

### Page-level drilldown

Define a relative parameterized path on the container and return a dynamic page:

```ts
export const servicesPage = new SceneAppPage({
  title: "Services",
  url: prefixRoute(ROUTES.Services),
  routePath: `${ROUTES.Services}/*`,
  getScene: () => servicesScene(),
  drilldowns: [
    {
      routePath: "service/:service/*",
      getPage(routeMatch, parent) {
        // SceneRouteMatch params come from React Router's useParams and are decoded.
        const service = routeMatch.params.service!;
        const encodedService = encodeURIComponent(service);

        return new SceneAppPage({
          title: service,
          subTitle: "Service detail",
          url: prefixRoute(`${ROUTES.Services}/service/${encodedService}`),
          routePath: "service/:service/*",
          getParentPage: () => parent,
          getScene: () => serviceScene(service),
        });
      },
    },
  ],
});
```

`getParentPage: () => parent` is the critical breadcrumb connection. A dynamic returned page is not automatically inserted as a child in the static scene tree.

Encode path data when building the link. `SceneRouteMatch.params` comes from React Router's `useParams`, so treat the parameter as decoded and re-encode it when building a canonical URL. Do not call `decodeURIComponent` blindly a second time; a valid decoded value such as `CPU 50%` can then throw. For a panel data link:

```ts
{
  title: "Open ${__value.text}",
  url: `${PLUGIN_BASE_URL}/${ROUTES.Services}/service/\${__value.text:percentencode}\${__url.params}`,
}
```

Do not interpolate decoded user/data values directly into a route path.

### Tab-level drilldown

Tab drilldowns have a non-obvious registration rule: `SceneAppPageRenderer` adds them to the container page's route list, not a nested `<Routes>` owned by the tab. Therefore a relative tab drilldown path must include the tab segment:

```ts
new SceneAppPage({
  title: "Handlers",
  url: prefixRoute(`${ROUTES.Services}/handlers`),
  routePath: "handlers/*",
  getScene: () => handlersScene(),
  drilldowns: [
    {
      // Include "handlers/" because this route is matched at container level.
      routePath: "handlers/:handler/*",
      getPage: (match, parent) => handlerPage(match, parent),
    },
  ],
});
```

An absolute app path that begins with the complete parent path can also work in React Router, and Grafana's own examples contain one, but the full relative container-level pattern is easier to reason about and test.

### Tabs inside a drilldown

The returned drilldown page can be another tab container. Give it `routePath` ending in `/*`, set `getParentPage`, use `""` for its first child tab, and use relative segments for siblings:

```ts
return new SceneAppPage({
  title: service,
  url: detailUrl,
  routePath: "service/:service/*",
  getParentPage: () => parent,
  tabs: [
    new SceneAppPage({
      title: "Metrics",
      url: detailUrl,
      routePath: "",
      getScene: () => metricsScene(service),
    }),
    new SceneAppPage({
      title: "Logs",
      url: `${detailUrl}/logs`,
      routePath: "logs",
      getScene: () => logsScene(service),
    }),
  ],
});
```

## Breadcrumb model

Breadcrumbs are built from `SceneAppPage` objects, not by splitting `location.pathname`.

```text
active tab
  └── container page becomes current pageNav item
      └── getParentPage() or SceneAppPage.parent
          └── next SceneAppPage ancestor
```

The renderer behaves as follows:

1. If the rendered page is a tab whose `parent` is a `SceneAppPage`, the parent container becomes the `pageNav` item.
2. The container's `title`, `url`, icon, subtitle, controls, and `hideFromBreadcrumbs` value drive the page header/breadcrumb item.
3. Its tabs become `pageNav.children` with an active flag. They are tab navigation, not additional breadcrumb ancestors.
4. Parent breadcrumb recursion follows `getParentPage()` when provided; otherwise it follows the scene object's `parent`, but only while that object is a `SceneAppPage`.
5. `hideFromBreadcrumbs` hides only the page where it is set. It does not repair or flatten a missing parent chain.

For a normal tab page, expect the breadcrumb/header item to say `Services`, while `Overview` and `Logs` appear as tabs. For a service drilldown, expect `Services > API`, provided the dynamic `API` page returns `getParentPage: () => servicesPage`.

Use `hideFromBreadcrumbs: true` only for a deliberate invisible grouping page. Default to visible for user-facing container and drilldown pages.

## URL state preservation

`SceneApp` URL sync handles stateful scene objects that opt in, including time range, time zone, refresh, and variables:

```ts
new SceneApp({
  pages: [...],
  urlSyncOptions: {
    updateUrlOnInit: true,
    createBrowserHistorySteps: true,
    namespace: "myapp",
    excludeFromNamespace: ["from", "to"],
  },
});
```

`preserveUrlKeys` controls what page, tab, and breadcrumb links retain:

- omitted/`undefined`: preserve all current query parameters;
- `[]`: preserve none;
- `['from', 'to', 'var-service']`: preserve only those keys.

This is a filter, not an additive list. When provided, every unlisted query key is removed from generated navigation URLs. Add `timezone`, refresh, and required variable keys deliberately.

Path routing remains in `location.pathname`; it is not controlled by `preserveUrlKeys`.

## Fallback routes

Every `SceneAppPage` renderer adds a `*` fallback. Unmatched child URLs show the built-in Not found page. Override it only when the app has a meaningful custom state:

```ts
new SceneAppPage({
  // ...
  getFallbackPage: () =>
    new SceneAppPage({
      title: "Not found",
      url: "",
      routePath: "*",
      getScene: () => notFoundScene(),
    }),
});
```

Do not use a fallback to mask malformed tab or drilldown paths. Test valid and invalid deep links directly.

## Manifest navigation

`plugin.json.includes` creates Grafana navigation entries; it does not define the internal `SceneApp` routes. Each included `path` must land on a matching top-level page, but internal tabs and drilldowns do not need manifest entries.

```json
{
  "type": "page",
  "name": "Services",
  "path": "/a/%PLUGIN_ID%/services",
  "addToNav": true
}
```

Keep these three values aligned:

```text
plugin.json path:  /a/%PLUGIN_ID%/services
SceneAppPage.url:  /a/<real-plugin-id>/services
routePath:         services/*
```

## Verification checklist

Test routing in a real Router context and, for plugin integration, in Grafana:

- Open every manifest URL directly, not only through client navigation.
- Open the bare tab-container URL and confirm the first tab is active.
- Open every sibling tab directly and use Back/Forward.
- Open a drilldown with spaces, slashes, `%`, Unicode, and other encoded characters supported by the identifier contract.
- Refresh a drilldown URL and confirm the same page, title, data, and breadcrumb chain render.
- Click every breadcrumb and tab while time/variables are set; verify exactly which query keys survive.
- Open an unknown child path and confirm the intended fallback.
- Assert breadcrumb page titles and active tab state in tests; do not only assert scene body text.
- Confirm one scene instance is not attached to two parents.

## Common failures

| Symptom                                                          | Cause                                                           | Fix                                                                              |
| ---------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Bare tab page is Not found                                       | Container lacks `/*` or child path is absolute                  | Use `<base>/*` and relative tab paths.                                           |
| Second tab does not match                                        | `routePath: "/logs"`                                            | Use `routePath: "logs"`.                                                         |
| First tab URL has an unwanted slash/segment                      | `routePath: "/"` or mismatched `url`                            | Use `routePath: ""` and the parent URL.                                          |
| Drilldown works but breadcrumb jumps to app root                 | Dynamic page has no parent chain                                | Return `getParentPage: () => parent`.                                            |
| Active tab title appears as a breadcrumb unexpectedly/not at all | Assuming tabs are breadcrumb pages                              | The container is the breadcrumb/pageNav item; tab titles are `pageNav.children`. |
| Container page vanishes from breadcrumbs                         | `hideFromBreadcrumbs: true` was copied from a template          | Remove it unless the container is intentionally invisible.                       |
| Tab-level drilldown is Not found                                 | Drilldown path omits the tab prefix                             | Match at container level with `tab/:id/*`.                                       |
| Time/variables disappear on tab click                            | `preserveUrlKeys` omitted required keys                         | Add every required key, or omit the property to preserve all.                    |
| Query junk persists across pages                                 | Assuming omitted `preserveUrlKeys` preserves nothing            | Set `preserveUrlKeys: []` or a narrow allowlist.                                 |
| App state resets on render/remount                               | SceneApp is recreated or `useSceneApp` factory identity changes | Use a module-scope factory or stable `useMemo`.                                  |
| Encoded identifier breaks links or queries                       | Raw value was inserted into a path or decoded twice             | Percent-encode links, use the decoded route param, and re-encode canonical URLs. |
