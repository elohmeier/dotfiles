# Plugin anatomy: file layout for a Grafana scenes app

This is the structure produced by `npx @grafana/create-plugin@latest` when you select the **App (with Scenes)** template, plus what each file does.

## Directory layout

```
my-scenes-app/
├── src/
│   ├── plugin.json                    # Plugin manifest (id, type, pages)
│   ├── module.tsx                     # Entry point — exports AppPlugin
│   ├── constants.ts                   # PLUGIN_BASE_URL, ROUTES, DATASOURCE_REF
│   ├── components/
│   │   ├── App/App.tsx                # Mounts SceneApp via useSceneApp
│   │   ├── AppConfig/AppConfig.tsx    # Org-admin config page (optional)
│   │   └── testIds.ts                 # data-testid constants
│   ├── pages/
│   │   ├── Home/
│   │   │   ├── homePage.ts            # SceneAppPage definition
│   │   │   ├── homeScene.ts           # EmbeddedScene factory
│   │   │   └── CustomSceneObject.tsx  # (optional) custom widget
│   │   ├── HelloWorld/...
│   │   ├── WithTabs/...
│   │   └── WithDrilldown/...
│   ├── utils/
│   │   ├── utils.plugin.ts            # PluginPropsContext
│   │   └── utils.routing.ts           # prefixRoute(route)
│   └── img/logo.svg
├── provisioning/
│   ├── datasources/default.yaml       # Auto-provision testdata
│   └── plugins/app.yaml               # Enable the plugin
├── tests/                             # Playwright e2e
├── package.json
├── tsconfig.json
├── docker-compose.yaml                # Spins up Grafana with plugin mounted
└── README.md
```

## `plugin.json`

The manifest Grafana reads to register the plugin. Fields specific to app plugins:

```json
{
  "$schema": "https://raw.githubusercontent.com/grafana/grafana/main/docs/sources/developers/plugins/plugin.schema.json",
  "type": "app",
  "name": "My Scenes App",
  "id": "myorg-myapp-app",
  "info": {
    "keywords": ["app"],
    "description": "",
    "author": { "name": "MyOrg" },
    "logos": { "small": "img/logo.svg", "large": "img/logo.svg" },
    "screenshots": [],
    "version": "%VERSION%",
    "updated": "%TODAY%"
  },
  "includes": [
    {
      "type": "page",
      "name": "Home",
      "path": "/a/%PLUGIN_ID%/home",
      "addToNav": true,
      "defaultNav": true
    },
    {
      "type": "page",
      "name": "Page with tabs",
      "path": "/a/%PLUGIN_ID%/page-with-tabs",
      "addToNav": true
    }
  ],
  "dependencies": {
    "grafanaDependency": ">=12.3.0",
    "plugins": []
  }
}
```

Key rules:

- `id` must be unique and follow the `<org>-<name>-app` convention (suffix `-app` is required for app plugins).
- Each entry in `includes` adds a sidebar navigation link. The first `defaultNav: true` page is the landing page.
- `path` uses `%PLUGIN_ID%` substitution at runtime.
- Every page listed here must correspond to a `SceneAppPage` URL (or a route handled by the App component). Otherwise the sidebar link 404s.
- `grafanaDependency` controls minimum Grafana version. Scenes apps typically require `>=10.4.0` for current API; the create-plugin template currently sets `>=12.3.0`.
- Add `"backend": true` and `"executable": "gpx_<name>"` if shipping a Go backend.

## `module.tsx` — entry point

```tsx
import { AppPlugin, type AppRootProps } from "@grafana/data";
import { initPluginTranslations } from "@grafana/i18n";
import { loadResources } from "@grafana/scenes";
import { LoadingPlaceholder } from "@grafana/ui";
import pluginJson from "plugin.json";
import React, { lazy, Suspense } from "react";
import type { AppConfigProps } from "./components/AppConfig/AppConfig";

await initPluginTranslations(pluginJson.id, [loadResources]);

const LazyApp = lazy(() => import("./components/App/App"));
const LazyAppConfig = lazy(() => import("./components/AppConfig/AppConfig"));

const App = (props: AppRootProps) => (
  <Suspense fallback={<LoadingPlaceholder text="" />}>
    <LazyApp {...props} />
  </Suspense>
);

const AppConfig = (props: AppConfigProps) => (
  <Suspense fallback={<LoadingPlaceholder text="" />}>
    <LazyAppConfig {...props} />
  </Suspense>
);

export const plugin = new AppPlugin<{}>().setRootPage(App).addConfigPage({
  title: "Configuration",
  icon: "cog",
  body: AppConfig,
  id: "configuration",
});
```

Why each piece exists:

- `await initPluginTranslations(...)` — top-level await is supported by Grafana's loader. Loads i18n catalogs (including scene translations via `loadResources`) before the App mounts. Safe to remove if not using i18n.
- `lazy(() => import(...))` — code-split the App and config UI so they don't block plugin load.
- `setRootPage(App)` — registers the App component as the handler for `/a/<plugin-id>/*`.
- `addConfigPage(...)` — optional plugin admin page at `/plugins/<plugin-id>?page=configuration`.

## `constants.ts`

```ts
import pluginJson from "./plugin.json";

export const PLUGIN_BASE_URL = `/a/${pluginJson.id}`;

export enum ROUTES {
  Home = "home",
  WithTabs = "page-with-tabs",
  WithDrilldown = "page-with-drilldown",
  HelloWorld = "hello-world",
}

export const DATASOURCE_REF = {
  uid: "gdev-testdata",
  type: "testdata",
};
```

Routes here must match the `path` segments in `plugin.json`'s `includes`.

## `package.json` essentials

```json
{
  "scripts": {
    "build": "webpack -c ./.config/webpack/webpack.config.ts --env production",
    "dev": "webpack -w -c ./.config/webpack/webpack.config.ts --env development",
    "test": "jest --watch --onlyChanged",
    "test:ci": "jest --passWithNoTests --maxWorkers 4",
    "typecheck": "tsc --noEmit",
    "lint": "eslint --cache .",
    "e2e": "playwright test",
    "server": "docker compose up --build",
    "sign": "npx --yes @grafana/sign-plugin@latest"
  },
  "dependencies": {
    "@emotion/css": "^11",
    "@grafana/data": "^12.4.2",
    "@grafana/i18n": "^12.4.2",
    "@grafana/runtime": "^12.4.2",
    "@grafana/scenes": "^6.x",
    "@grafana/ui": "^12.4.2",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.22.0",
    "rxjs": "^7.8"
  }
}
```

The `@grafana/*` packages must all match the same minor version. Grafana validates the plugin's compiled bundle against the running Grafana version's exposed API.

## `provisioning/`

Auto-loaded when running `docker compose up`:

```yaml
# provisioning/datasources/default.yaml
apiVersion: 1

datasources:
  - name: gdev-testdata
    isDefault: true
    type: testdata
```

```yaml
# provisioning/plugins/app.yaml
apiVersion: 1

apps:
  - type: myorg-myapp-app
    org_id: 1
    org_name: Main Org.
    disabled: false
    jsonData: {}
```

## `docker-compose.yaml`

The create-plugin template provides this so `npm run server` boots a Grafana with the plugin volume-mounted. Plugin id and tag substitution happen at build time. The user does not normally need to edit it.

## Build tooling

The create-plugin template uses `webpack` (or `rspack`) configured at `.config/webpack/webpack.config.ts`. Don't edit `.config/` directly — use `webpack.config.ts` at the project root for project-specific overrides. The template provides one that re-exports the default config.

## Testing

- Unit tests: Jest, colocated as `*.test.ts(x)`.
- E2E: `@grafana/plugin-e2e` (Playwright) under `tests/`. Each test loads the plugin in a real Grafana instance.

```ts
// tests/appNavigation.spec.ts
import { expect, test } from "@grafana/plugin-e2e";

test("navigates to home", async ({ gotoAppPage }) => {
  const page = await gotoAppPage({ path: "/home" });
  await expect(page.getByText("Home page")).toBeVisible();
});
```
