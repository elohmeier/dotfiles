---
name: grafana
description: Work with Grafana dashboards and Grafana app plugins. Use when Codex needs to design, review, create, edit, convert, or validate dashboard JSON and panels, including stable dashboard.grafana.app/v2 conversion, canonical and Grafana code-editor compatibility validation, native tabbed layouts, table/stat sparklines, and live visible-data checks; tune PromQL-backed dashboards, transformations, variables, thresholds, legends, tables, and links; or build Grafana app plugins with @grafana/scenes, including SceneApp routing, breadcrumbs, SceneAppPage tabs and drilldowns, EmbeddedScene composition, VizPanel/PanelBuilders, scene variables, SceneQueryRunner, SceneDataTransformer, layouts, custom SceneObjectBase classes, behaviors, URL sync, and @grafana/scenes-react.
---

# Grafana

Use this skill for Grafana work across two related domains:

- **Dashboards and panel JSON**: dashboard design, layout, visualization choice, PromQL panel tuning, transformations, variables, field config, overrides, table setup, links, thresholds, legends, and rendering behavior.
- **Grafana app plugins with @grafana/scenes**: app scaffolding, SceneApp routing, pages, tabs, drilldowns, scene composition, variables, queries, transformations, layouts, custom scene objects, behaviors, URL sync, and the `@grafana/scenes-react` API.

If the user is building a panel plugin or datasource plugin instead of a scenes app, this skill only applies to the Grafana concepts around panels and data shape; point them at `@grafana/create-plugin` for plugin-specific scaffolding.

## Choose the Track

Before loading references, classify the task:

- Dashboard JSON, existing dashboards, panel behavior, PromQL panels, variables, transformations, field config, table/data-link work: use the dashboard track.
- Grafana app plugins, `@grafana/scenes`, routing, SceneAppPage, EmbeddedScene, VizPanel, PanelBuilders, scene variables, custom scene objects, scenes-react: use the scenes app track.
- Both can apply when building a scenes app that embeds dashboard-like panels. In that case, use scenes references for app structure and dashboard references for panel/data-shape decisions.

## Installed tools

Executable tools are maintained in `elohmeier/dotfiles` and installed on PATH by chezmoi. Use `grafana-dashboard` for migration and canonical/live validation, `grafana-inspect` for structure, data, and upstream editor checks, `grafana-query` for API operations/proxies, and `grafana-users` for server administration. Run their help/version commands to inspect the installed interface and Grafana pin. Do not install dependencies inside this skill or invoke skill-local scripts.

## Dashboard Track

First steps:

1. Write the design contract before writing queries: audience, job or decision, trigger, normal/concerning/critical states, freshness, failure-state semantics, next action, owner, and success criteria. Start from `assets/dashboard/dashboard-design-brief.md`.
2. Choose one operational strategy and information path. Separate dashboards when audiences, decisions, or time horizons differ; do not solve that mismatch with more rows or tabs.
3. Identify the data shape before choosing a panel: time series, single reduced value, rows and columns, logs, traces, geospatial, histogram buckets, categorical states, or node/edge graph.
4. Prefer fixing data shape at the query when it is cheap and semantically clear. Use transformations when joining, reshaping, hiding, renaming, calculating, or adapting mixed data for one panel.
5. Set units, decimals, thresholds, value mappings, legend, tooltips, null/no-data behavior, and field overrides deliberately. These determine whether the panel is truthful and readable.
6. Validate with representative tasks and data states. Inspect final data frames in panel Inspect/Data and transformation debug; also test normal, incident, zero, no-data, stale, partial-data, and query-error states.

Dashboard references:

- [references/dashboard/rendering-model.md](references/dashboard/rendering-model.md): how Grafana panel JSON becomes rendered React panels, including query, transformation, field config, `PanelChrome`, and plugin behavior.
- [references/dashboard/dashboard-design.md](references/dashboard/dashboard-design.md): design contracts, workflow and layout choices, failure states, accessibility, performance budgets, navigation, and task-based review.
- [references/dashboard/panel-types.md](references/dashboard/panel-types.md): what each core visualization is good for, required data shape, and common configuration details.
- [references/dashboard/queries-and-transformations.md](references/dashboard/queries-and-transformations.md): PromQL handling, series naming, query options, variables, transformations, tables, joining, reducing, and field overrides.
- [references/dashboard/tables-and-sparklines.md](references/dashboard/tables-and-sparklines.md): exact table option ownership, table-sparkline nested-frame contract, `timeSeriesTable`, stat sparkline behavior, JSON, Scenes builders, and troubleshooting.
- [references/dashboard/tabbed-dashboards-json.md](references/dashboard/tabbed-dashboards-json.md): how to author native tabbed dashboards in `dashboard.grafana.app/v2` JSON, including element references, child layouts, nesting, repeats, URL state, import, and validation.
- [references/dashboard/dashboard-visible-data.md](references/dashboard/dashboard-visible-data.md): query classic or v2 dashboards against live Grafana and inspect transformed, field-configured values with the visible-data CLI.
- [references/dashboard/generated-dashboard-management.md](references/dashboard/generated-dashboard-management.md): generated dashboards, Jsonnet/source-of-truth provenance, metadata annotations, managed dashboards, and plugin-owned dashboards.
- [references/dashboard/dashboard-v2-tooling.md](references/dashboard/dashboard-v2-tooling.md): correctness-first classic/v1-to-stable-v2 conversion, explicit server context, loss auditing, conversion-first Jsonnet, local Grafana validation, and strict live dry runs.

Reusable dashboard JSON starts in `assets/dashboard/`:

- `assets/dashboard/dashboard-design-brief.md`: fill-in design contract and review worksheet to complete before dashboard JSON.
- `assets/dashboard/service-red-dashboard.json`: RED service dashboard skeleton for Prometheus.
- `assets/dashboard/service-red-dashboard-v2.json`: full `dashboard.grafana.app/v2` RED example with rows, fixed and auto grids, variables, explicit failure semantics, and operational descriptions.
- `assets/dashboard/infrastructure-use-dashboard.json`: USE infrastructure dashboard skeleton for Prometheus/node exporter.
- `assets/dashboard/table-detail-panel.json`: table panel template with organize/filter-friendly defaults.
- `assets/dashboard/panel-snippets.json`: copyable panel fragments for common stat, time series, table, and text panels.
- `assets/dashboard/table-sparklines-v2.json`: schema-v2 dashboard with a correctly transformed table sparkline and an unreduced stat sparkline.
- `assets/dashboard/tabbed-dashboard-v2.json`: complete, schema-valid `dashboard.grafana.app/v2` resource with fixed-grid and auto-grid tabs.
- `assets/dashboard/v2.libsonnet`: thin stable-v2 constructors for direct authoring; never a classic converter.
- `assets/dashboard/prometheus.libsonnet`: stable-v2 Prometheus queries, variables, and transformations; configure a datasource UID explicitly or with `withDefaultDatasource`.
- `assets/dashboard/conversion-context.example.json`: generic datasource/library snapshot shape required by the converter.

Dashboard workflow:

1. Complete the dashboard design contract: audience, decision, trigger, time/freshness contract, state semantics, next action, owner, and measurable task outcome.
2. Start with one observability strategy: RED for services, USE for infrastructure, and golden signals for user-facing systems.
3. Build the action path: notice status, interpret correlated trends, inspect detail, then reach the runbook or logs/traces/profiles without losing time and variable context.
4. Choose the grouping primitive deliberately: separate dashboard, tabs, rows, fixed grid, auto grid, repeats, or conditional rendering. Keep operational status visible; do not hide critical evidence behind tabs or conditions.
5. Choose panels by data shape. Use time series for numeric values over time, stat/gauge/bar gauge for reduced values, table for row-level detail, state timeline/status history for categorical state over time, and heatmap/histogram for distributions. Read `references/dashboard/tables-and-sparklines.md` before putting trends inside stats or table cells.
6. Configure query output with stable `refId`s, bounded labels, Prometheus `$__rate_interval` for `rate()` and `increase()`, and query format/type matching the panel.
7. Shape and label fields with transformations in intentional order and field overrides for units, decimals, display names, min/max, colors, thresholds, no-value text, and panel-specific options.
8. Set and verify a performance budget for default time range, refresh, panel/query count, series cardinality, variable chains, repeats, transformations, and maximum data points.
9. Validate the dashboard through representative user tasks and failure states, at narrow and wide widths and in light and dark themes.

Dashboard JSON guardrails:

- Panels persist `type`, `title`, `gridPos`, `targets`, `datasource`, `options`, `fieldConfig`, `transformations`, `links`, time overrides, and repeat settings.
- `fieldConfig` should contain `defaults` and `overrides`; do not put display-only changes in query strings when field config can express them.
- Query `targets` need stable `refId`s because transformations and expressions often reference them.
- Use `gridPos` units on a 24-column grid. Keep related panels aligned and avoid tiny panels for dense legends or tables.
- When changing panel type, review `options` and `fieldConfig.custom`; panel-specific custom options may not apply to the new panel.
- For generated classic dashboards, keep the top-level dashboard `id` nullable or absent when importing into a new Grafana instance unless targeting an existing dashboard. V2 panel `spec.id` fields are different: they are required numeric panel identities.
- For Jsonnet/GitOps/generated dashboards, read `references/dashboard/generated-dashboard-management.md` before recommending custom dashboard fields or edit-lock behavior.
- Native dashboard tabs require the v2 resource model: use `spec.elements` plus a `TabsLayout`. Classic dashboard JSON with top-level `panels`/`schemaVersion` has no native tab representation and downgrades tabs to rows.
- A table sparkline cell needs a frame-valued field. Keep a range query, run `timeSeriesTable`, and apply `custom.cellOptions.type: "sparkline"` only to `Trend #<refId>` or its renamed final field.
- A stat sparkline needs the original range data. Use `graphMode: "area"` with `reduceOptions.values: false`; do not collapse the field with an upstream reduce transformation.

Dashboard schema validation:

- Read `references/dashboard/dashboard-v2-tooling.md` before converting or generating v2 JSON.
- Use `grafana-dashboard convert` for classic or v1 inputs. It runs Grafana's pinned migration and direct stable-v2 converter, requires a complete datasource/library context, validates with Grafana's CUE validator, and fails its own preservation audit. Do not convert dashboards with Jsonnet.
- Use `grafana-dashboard validate` for deterministic local checks against the pinned stable-v2 Go types and Grafana validator. Pass `--input-format resource` or `--input-format spec` explicitly.
- Use `grafana-inspect editor-schema` before pasting or applying v2 JSON through Grafana's code editor. It executes the pinned upstream schema converter and Monaco JSON worker and can reject JSON that the canonical CUE validator accepts.
- Use `grafana-dashboard validate-live` for the authoritative `dryRun=All&fieldValidation=Strict` check against the target Grafana namespace.
- Stable v2 is the target. Do not produce `v2alpha1` or `v2beta1` for new work and do not preserve obsolete helper interfaces.

Dashboard live-data validation:

- Use `grafana-inspect data` after schema validation to query a live Grafana instance and inspect the values users receive after variables, standard transformations, field overrides, units, mappings, reducers, and table sorting.
- Use `grafana-inspect editor-diagnostics` for panels with transformations when Grafana editor diagnostics must participate in validation. It supplies one synthetic frame per query and mounts the tool-pinned Grafana release's real transformation rows and editors under jsdom, so neither a Grafana server nor a source-path environment variable is required. It caches the pinned upstream source/runtime automatically on first use and fails on semantic editor alerts such as ineffective transformations. Do not replace it with dashboard-specific warning rules.
- Data and transformation-editor checks support classic and v2 dashboard JSON. Start live-data work with `grafana-inspect data --list-panels`, then select bounded panels, time ranges, and variable scopes. Do not run every panel against production by default.
- Editor diagnostics need no connection configuration; configure `GRAFANA_URL` and `GRAFANA_TOKEN` for live data checks. Dependencies are installed by the dotfiles tools. Keep tokens out of arguments, output, and version control.
- The automatically cached Grafana release is trusted upstream code pinned by the dotfiles tools. Use only a trusted checkout when overriding it with `--grafana-source`: the headless harness executes that checkout's Jest configuration and frontend code.
- This is a data-pipeline check, not a browser renderer. Pair it with task-based browser checks for layout, interaction, links, themes, narrow widths, and accessibility. Read `references/dashboard/dashboard-visible-data.md` for setup, examples, limitations, and exit codes.

## Scenes App Track

First steps:

1. Identify whether the user is scaffolding a new app, adding to an existing app, debugging scenes behavior, or choosing between APIs.
2. Read only the relevant reference file from `references/scenes/`.
3. Adapt a template from `templates/` when writing app files. Always rename `${...}` placeholders before writing files.
4. Verify Grafana version, datasource, bundler, and package versions against `grafanaDependency` in `plugin.json`.

API choice:

| API                     | When to use                                                                          | Style                                                                    |
| ----------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `@grafana/scenes`       | Default. Full feature set: SceneApp routing, drilldowns, tabs, complex scene graphs. | Imperative: instantiate scene objects and compose a tree.                |
| `@grafana/scenes-react` | Lighter apps, React-first teams, simple dashboards with hooks. WIP/newer.            | Declarative: `<SceneContextProvider>`, `<VizPanel>`, `useQueryRunner()`. |

When unsure, recommend `@grafana/scenes`; it is the mature API and matches the official create-plugin template.

Quick scaffold workflow for a new scenes app:

```bash
npx @grafana/create-plugin@latest
# Select: "App (with Scenes)" template
# Provide: org name, plugin name
cd <plugin-dir>
npm install
npm run server
npm run dev
```

If the user cannot or does not want to run `create-plugin`, copy `templates/plugin-skeleton/` plus `templates/scene-app/` and update placeholders.

Scenes references:

| File                                              | Use when                                                                                      |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `references/scenes/01-plugin-anatomy.md`          | Setting up a new plugin: `plugin.json`, `module.tsx`, scripts, dependencies, provisioning     |
| `references/scenes/02-scene-app-routing.md`       | `SceneApp`, `SceneAppPage`, `useSceneApp`, tabs, drilldowns, breadcrumbs, URL sync            |
| `references/scenes/03-scene-objects-and-state.md` | Core concepts: `SceneObjectBase`, state, `useState()`, parent/child, `sceneGraph`, activation |
| `references/scenes/04-data-and-queries.md`        | `SceneQueryRunner`, `SceneDataTransformer`, data layers, time range, datasource refs          |
| `references/scenes/05-variables.md`               | Variable types, `SceneVariableSet`, `VariableValueSelectors`, interpolation, macros           |
| `references/scenes/06-layouts.md`                 | `SceneFlexLayout`, `SceneCSSGridLayout`, `SceneGridLayout`, `SplitLayout`, responsive `md`    |
| `references/scenes/07-panels-and-viz.md`          | `VizPanel`, `PanelBuilders`, options, fieldConfig, panel menu, runtime panel plugins          |
| `references/scenes/08-custom-scene-objects.md`    | Building a `SceneObjectBase` subclass with state, renderer, activation handlers               |
| `references/scenes/09-behaviors.md`               | `$behaviors`, `ActWhenVariableChanged`, `CursorSync`, `LiveNowTimer`, custom behaviors        |
| `references/scenes/10-scenes-react.md`            | Hooks/component API: `SceneContextProvider`, `useQueryRunner`, `<VizPanel>`                   |

Template index:

| Path                                       | What it gives you                                                                                               |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `templates/plugin-skeleton/`               | Bare `plugin.json`, `module.tsx`, `constants.ts`, `utils/` for any scenes app                                   |
| `templates/scene-app/`                     | Full `App.tsx` plus `pages/Home/{homePage,homeScene}.ts` wiring `SceneApp` to `SceneAppPage` to `EmbeddedScene` |
| `templates/scene-app/pages/WithTabs/`      | Page with tabs                                                                                                  |
| `templates/scene-app/pages/WithDrilldown/` | Page with dynamic drilldown route (`:param`)                                                                    |
| `templates/custom-scene-object/`           | Reusable `SceneObjectBase` subclass with state, renderer, activation handler                                    |
| `templates/scenes-react/`                  | Equivalent app built with `@grafana/scenes-react` hooks                                                         |

Scenes guardrails:

- Never share scene object instances across multiple parents. To use the same logical object in two places, `clone()` it or wrap it with `SceneObjectRef`.
- Keep one stable `SceneApp` instance. Prefer `useSceneApp(getSceneApp)` with a module-scope factory; its cache key is the factory identity, so never pass an inline factory.
- Match versions. `@grafana/data`, `@grafana/runtime`, `@grafana/ui`, and `@grafana/scenes` must be compatible with `grafanaDependency` in `plugin.json`.
- Provision a datasource for dev apps that query data. The create-plugin template uses `gdev-testdata`; add `provisioning/datasources/default.yaml` when needed.
- `module.tsx` uses top-level `await` for `initPluginTranslations(...)` before `App` lazy-loads. Do not move the import below the lazy-loaded component.
- Pages with tabs or drilldowns need `routePath: '<base>/*'`. Child paths are relative: use `''` for the first tab and `logs`, never `'/'` or `'/logs'`, for sibling tabs.
- Dynamic drilldown pages must return `getParentPage: () => parent` for breadcrumbs. Tab drilldowns are registered at the container route level, so their relative pattern includes the tab segment, for example `handlers/:handler/*`.
- The tab container supplies the breadcrumb/page header item; active tabs are navigation children. Do not set `hideFromBreadcrumbs: true` just because a page has tabs.

## Validation

For dashboard work, confirm the dashboard has a named audience, decision, owner, freshness contract, explicit failure-state semantics, action path, and performance budget. Confirm each panel has a clear question, matching data shape, correct units/thresholds/legends/null handling, bounded PromQL cardinality, predictable table columns, useful data links, and intentional transformation order. Test the representative task and normal, incident, zero, no-data, stale, partial-data, and query-error states.

For scenes apps, run the repo's lint, typecheck, and tests when available. For UI changes, start the app if practical and verify routing, panels, variables, query behavior, URL sync, and responsive layout.
