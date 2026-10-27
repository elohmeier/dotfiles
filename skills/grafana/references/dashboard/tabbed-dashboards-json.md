# Tabbed dashboard JSON

Use this when creating, reviewing, importing, or generating a Grafana dashboard with native horizontal tabs. This is dashboard JSON, not `SceneAppPage` routing or tabs in a Grafana app plugin.

## Contents

- [Source anchors](#source-anchors)
- [Support boundary](#support-boundary)
- [Mental model](#mental-model)
- [Minimal tab layout](#minimal-tab-layout)
- [Choose each tab's child layout](#choose-each-tabs-child-layout)
- [Construction workflow](#construction-workflow)
- [Selection and URL state](#selection-and-url-state)
- [Repeated tabs and section variables](#repeated-tabs-and-section-variables)
- [Import and validation](#import-and-validation)

## Source anchors

- Stable v2 schema: `apps/dashboard/pkg/apis/dashboard/v2/dashboard_spec.cue`
- Tab serialization: `public/app/features/dashboard-scene/serialization/layoutSerializers/TabsLayoutSerializer.ts`
- Fixed-grid and auto-grid serializers: `public/app/features/dashboard-scene/serialization/layoutSerializers/DefaultGridLayoutSerializer.ts` and `AutoGridLayoutSerializer.ts`
- Runtime selection and URL sync: `public/app/features/dashboard-scene/scene/layout-tabs/TabsLayoutManager.tsx`
- Rendering: `public/app/features/dashboard-scene/scene/layout-tabs/TabsLayoutManagerRenderer.tsx`
- Import handling: `public/app/features/manage-dashboards/import/components/DashboardImportK8s.tsx`
- Representative fixtures: `e2e-playwright/dashboards/V2DashWithTabs.json` and `apps/dashboard/pkg/migration/conversion/testdata/input/v2beta1.tabs-with-nested-rows.json`

## Support boundary

Native tabs belong to the `dashboard.grafana.app/v2` resource schema. Prefer the stable resource shape:

```json
{
  "apiVersion": "dashboard.grafana.app/v2",
  "kind": "Dashboard",
  "metadata": { "name": "service-overview" },
  "spec": { "...": "dashboard spec" }
}
```

Do not add `TabsLayout` to classic dashboard JSON containing top-level `panels` and `schemaVersion`; the classic v1 model has no native tab concept. Grafana's v2-to-v1 conversion turns each tab into an expanded row and flattens its content, so a downgrade does not preserve tab behavior.

The full copyable starting point is [../../assets/dashboard/tabbed-dashboard-v2.json](../../assets/dashboard/tabbed-dashboard-v2.json). It contains two text panels so the tab structure can be tested without a datasource.

## Mental model

The panel definitions and their placement are separate:

```text
spec.elements["panel-overview"]  <- panel definition
spec.elements["panel-details"]   <- panel definition

spec.layout (TabsLayout)
  tab 1 -> child GridLayout     -> ElementReference("panel-overview")
  tab 2 -> child AutoGridLayout -> ElementReference("panel-details")
```

Tabs do not contain panel objects. Every layout item contains an `ElementReference` whose `name` exactly matches a key in `spec.elements`.

## Minimal tab layout

Use a `TabsLayout` at the dashboard root when the entire dashboard is tabbed:

```json
{
  "kind": "TabsLayout",
  "spec": {
    "tabs": [
      {
        "kind": "TabsLayoutTab",
        "spec": {
          "title": "Overview",
          "layout": {
            "kind": "GridLayout",
            "spec": {
              "items": [
                {
                  "kind": "GridLayoutItem",
                  "spec": {
                    "x": 0,
                    "y": 0,
                    "width": 24,
                    "height": 8,
                    "element": {
                      "kind": "ElementReference",
                      "name": "panel-overview"
                    }
                  }
                }
              ]
            }
          }
        }
      },
      {
        "kind": "TabsLayoutTab",
        "spec": {
          "title": "Details",
          "layout": {
            "kind": "AutoGridLayout",
            "spec": {
              "maxColumnCount": 3,
              "columnWidthMode": "standard",
              "rowHeightMode": "standard",
              "items": [
                {
                  "kind": "AutoGridLayoutItem",
                  "spec": {
                    "element": {
                      "kind": "ElementReference",
                      "name": "panel-details"
                    }
                  }
                }
              ]
            }
          }
        }
      }
    ]
  }
}
```

Assign this object to `spec.layout`; it is not a complete dashboard by itself.

## Choose each tab's child layout

Each `TabsLayoutTab.spec.layout` is required and may be any of these recursively:

- `GridLayout`: exact 24-column placement. Every item requires integer `x`, `y`, `width`, and `height` plus an element reference.
- `AutoGridLayout`: responsive placement. Set `columnWidthMode` and `rowHeightMode`; use `columnWidth` or `rowHeight` only when the corresponding mode is `custom`.
- `RowsLayout`: one tab can contain multiple collapsible or titled rows. Each `RowsLayoutRow` owns another child layout.
- `TabsLayout`: nested tabs are schema-valid. Use them sparingly because the active-tab URL key and the interface become more complex.

Tabs may also be nested inside a row by putting a `TabsLayout` in `RowsLayoutRow.spec.layout`. The dashboard root itself may be `GridLayout`, `AutoGridLayout`, `RowsLayout`, or `TabsLayout`.

## Construction workflow

1. Start from the v2 resource asset or an exported v2 dashboard, and keep `apiVersion`, `kind`, `metadata`, and `spec` separate.
2. Put every `Panel` or `LibraryPanel` in `spec.elements` under a stable unique key such as `panel-request-rate`.
3. Give regular panels unique numeric `spec.id` values. The map key is the layout reference; the numeric ID remains panel runtime identity.
4. Build `spec.layout` as a `TabsLayout`, preserving the intended tab order in `spec.tabs`.
5. Give each tab a title and a complete child layout. Add layout items that reference `spec.elements` keys.
6. Check that every referenced key exists, every intended panel is reachable from the layout, and a panel is not accidentally placed in multiple tabs.
7. Validate the finished resource against the same Grafana version that will load it.

Do not mix v1 names into v2 layout items: fixed-grid dimensions are `width` and `height`, not `w` and `h`, and placement belongs to `GridLayoutItem.spec`, not to a panel's `gridPos`.

## Selection and URL state

The selected tab is runtime URL state, not persisted dashboard state:

- The first tab is selected when no URL value matches.
- Do not invent `activeTab`, `selected`, `id`, or `index` fields in tab JSON; the schema has none.
- A top-level tabs layout uses the `dtab` query parameter. For example, `?dtab=Details` selects a tab titled `Details`.
- Nested tab managers prefix `dtab` with ancestor row/tab slugs, for example `?Overview-dtab=Logs`.
- Current slugs replace runs of spaces with `-` but retain punctuation. Duplicate slugs receive suffixes such as `__2`. Grafana also accepts legacy lowercased, punctuation-stripped slugs for old links.

Keep sibling tab titles unique and reasonably stable if links select tabs. Titles may interpolate variables, especially for repeated tabs, so verify the resulting URL behavior.

## Repeated tabs and section variables

To repeat a tab for a dashboard variable, add `repeat` to the source tab:

```json
{
  "kind": "TabsLayoutTab",
  "spec": {
    "title": "Instance $instance",
    "repeat": {
      "mode": "variable",
      "value": "instance"
    },
    "layout": {
      "kind": "AutoGridLayout",
      "spec": {
        "columnWidthMode": "standard",
        "rowHeightMode": "standard",
        "items": []
      }
    }
  }
}
```

`value` is the variable name, not `$instance`. Define that variable in `spec.variables`; multi-value variables generate one runtime tab per selected value. Persist only the source tab—Grafana creates repeat clones at runtime and filters clones out during normal serialization.

Stable v2 also permits a `variables` array on `TabsLayoutTab.spec`. Those section variables are scoped to the tab and its descendant layouts. Do not assume this field exists in older `v2alpha1` documents; prefer stable v2 and validate against the target version.

Tabs also accept `conditionalRendering`, using the same conditional-rendering group kind as rows and auto-grid items. Copy its shape from a target-version export or schema rather than guessing it.

## Import and validation

Grafana's JSON import detects a v2 resource, unwraps its `spec`, and preserves the resource `metadata.name` as the dashboard UID. The target must have new dashboard layouts enabled; current Grafana source marks `dashboardNewLayouts` generally available and enabled by default, while older or customized installations can reject a new-layout import.

For API creation, send the resource wrapper to the versioned resource endpoint, for example:

```text
POST /apis/dashboard.grafana.app/v2/namespaces/<namespace>/dashboards
```

Use `kind: "Dashboard"` for create/update payloads. `DashboardWithAccessInfo` is a DTO/read shape, not the authoring shape.

Validate a complete resource or raw `spec` with the skill script:

```bash
grafana-dashboard validate \
  --input assets/dashboard/tabbed-dashboard-v2.json \
  --input-format resource
```

For the authoritative target-server check, follow with:

```bash
grafana-dashboard validate-live \
  --input assets/dashboard/tabbed-dashboard-v2.json \
  --namespace default
```

It uses strict field validation and a dry run.

Also inspect references mechanically when generating JSON:

```bash
jq -r '.spec.layout | .. | objects | select(.kind? == "ElementReference") | .name' dashboard.json
jq -r '.spec.elements | keys[]' dashboard.json
```

The two lists should contain the same names exactly once. The central validator checks that invariant as well as schema structure and required fields; it does not replace loading the dashboard in the target Grafana and checking tab order, selection links, queries, variables, and responsive layout.
