# Templates

Copy-paste-ready scaffolding for a Grafana scenes app.

## Placeholders

All templates use these placeholders. Replace them when copying:

| Placeholder          | Example                         | Where it appears      |
| -------------------- | ------------------------------- | --------------------- |
| `${PLUGIN_ID}`       | `myorg-myapp-app`               | `plugin.json`, paths  |
| `${PLUGIN_NAME}`     | `My Scenes App`                 | `plugin.json`, README |
| `${ORG_NAME}`        | `MyOrg`                         | `plugin.json`         |
| `${DATASOURCE_UID}`  | `gdev-testdata` or `prometheus` | scene query runners   |
| `${DATASOURCE_TYPE}` | `testdata` or `prometheus`      | scene query runners   |

## Templates

### `plugin-skeleton/`

Minimal plugin shell. Use when the user wants to wire scenes into something not built with `create-plugin`, or to understand the bare minimum.

Files:

- `plugin.json`
- `module.tsx`
- `constants.ts`
- `utils/utils.routing.ts`
- `utils/utils.plugin.ts`

### `scene-app/`

Full `SceneApp` wiring with home, tabs, and drilldown pages.

Files:

- `components/App/App.tsx`
- `pages/Home/{homePage,homeScene}.ts`
- `pages/HelloWorld/{helloWorldPage,helloWorldScene}.ts`
- `pages/WithTabs/withTabsPage.ts`
- `pages/WithDrilldown/{withDrilldownPage,withDrilldownScene,roomDetailScene}.ts`

### `custom-scene-object/`

A reusable `SceneObjectBase` subclass with state, renderer, activation handler, and URL sync.

### `scenes-react/`

The same hello-world app built with `@grafana/scenes-react` hooks instead of the imperative API.

## Recommended workflow

1. Run `npx @grafana/create-plugin@latest` and select **App (with Scenes)**. This produces the canonical project layout, including build config, tests, and Docker.
2. Replace the generated `pages/` and `components/App/App.tsx` with the templates here if you want a leaner starting point.
3. For ad-hoc additions to an existing app, copy individual page templates into `src/pages/<NewPage>/`.
