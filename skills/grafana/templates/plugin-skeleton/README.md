# Plugin skeleton

Bare minimum for a Grafana app plugin that hosts scenes.

## Files

```
plugin.json                Manifest registered with Grafana
module.tsx                 Entry point — exports AppPlugin
constants.ts               Route enum, plugin base URL, datasource ref
utils/utils.routing.ts     prefixRoute(route) helper
utils/utils.plugin.ts      PluginPropsContext for accessing AppRootProps
```

## Placeholders

Replace before building:

- `${PLUGIN_ID}` — `<org>-<name>-app` (e.g., `myorg-monitoring-app`)
- `${PLUGIN_NAME}` — Human-readable name
- `${ORG_NAME}` — Author/org name
- `${DATASOURCE_UID}` / `${DATASOURCE_TYPE}` — your default datasource

## What's missing

This skeleton has no `App.tsx` or pages. Layer the `scene-app/` template (or your own) on top, then add a `provisioning/` directory and `package.json` from `@grafana/create-plugin`'s scenes-app template.

If you're starting fresh, run `npx @grafana/create-plugin@latest` and pick **App (with Scenes)** instead of assembling this manually.
