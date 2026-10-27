# Stable Dashboard v2 Tooling

Use `grafana-dashboard` for stable `dashboard.grafana.app/v2` conversion, canonical and code-editor validation, strict live validation, and conversion-first Jsonnet rendering. The tool imports Grafana's own dashboard migration, conversion, generated Go types, OpenAPI definitions, and embedded CUE validator at the module revision printed by:

```bash
grafana-dashboard version
```

The converter intentionally does not support `v2alpha1`, `v2beta1`, approximate conversion, or compatibility with the retired helper interfaces.

The commands are installed by the dotfiles repository. Conversion and canonical validation run a compiled Go binary and need no source checkout or Go toolchain at invocation time. Only `render` additionally requires `jsonnet`. Advanced editor checks lazily cache the exact pinned Grafana source and frontend runtime.

## Conversion contract

Classic input follows Grafana's own sequence:

1. Run all classic schema migrations through Grafana's current `LATEST_VERSION`.
2. Assign unique panel IDs with Grafana's migration helper.
3. Wrap the migrated model as a v1 dashboard resource.
4. Call Grafana's direct v1-to-stable-v2 converter.
5. Validate the resulting stable-v2 spec with Grafana's embedded CUE validator.
6. Fail if the preservation audit detects changed or missing panels, query `refId`s, transformations, plugin IDs/versions, annotations, links, variables, library references, or layout references.

For a v1 resource, the tool starts at step 3 because a served v1 resource is already expected to contain the current classic schema model.

Grafana conversion depends on server-side datasource and library-element indexes. Never replace these with guessed plugin types, default UIDs, or hard-coded plugin versions. Export a complete snapshot from the same organization/namespace that owns the dashboard:

```bash
export GRAFANA_URL=https://grafana.example.test
export GRAFANA_TOKEN=...
grafana-dashboard export-context --output conversion-context.json
```

The token must be able to list every datasource and library element that the Grafana conversion service would see. The snapshot contains no datasource secrets. Commit it only if datasource names, UIDs, folder UIDs, and library panel models are acceptable repository data.

Convert raw classic dashboard JSON:

```bash
grafana-dashboard convert \
  --input dashboard.json \
  --input-format classic \
  --context conversion-context.json \
  --name service-overview \
  --namespace default \
  --output dashboard.v2.json
```

Use `--input-format export` for the legacy HTTP response shape with a top-level `dashboard` property, or `--input-format v1` for a `dashboard.grafana.app/v1` or `v1beta1` resource. Use `--output-format spec` only when a downstream generator explicitly owns the wrapper.

The example at `assets/dashboard/conversion-context.example.json` documents the context shape. Both catalog sections must say `"complete": true`; this is a deliberate assertion, not a way to make a partial catalog valid.

## Jsonnet after conversion

Jsonnet is an authoring and patching layer, not a schema converter. Do not implement classic-to-v2 conversion in Jsonnet and do not add a `normalize` function that guesses missing Grafana context.

For a converted baseline, have the Jsonnet source load the file supplied by the render command:

```jsonnet
local base = std.extVar('grafanaDashboardV2');

base {
  title: base.title + ' (generated)',
}
```

Then render it through the same conversion and validation boundary:

```bash
grafana-dashboard render \
  --input dashboard.json \
  --input-format classic \
  --context conversion-context.json \
  --name service-overview \
  --jsonnet dashboard.jsonnet \
  --jpath assets/dashboard \
  --output dashboard.generated.json
```

`render` supplies `grafanaDashboardV2` as Jsonnet code from a temporary JSON file, validates the rendered stable-v2 spec with Grafana's validator, and verifies that every element is referenced by the layout exactly once. Intentional query changes happen after the baseline preservation audit.

For new dashboards, author stable v2 directly. `assets/dashboard/v2.libsonnet` contains thin schema-shaped constructors; `assets/dashboard/prometheus.libsonnet` contains Prometheus query and transformation helpers. They require datasource UIDs and plugin versions at the call site. They contain no converter, environment defaults, or hidden normalization.

## Validation levels

Local validation uses the pinned generated stable-v2 Go types, Grafana's embedded `ValidateDashboardSpec` CUE validator, and an exact layout-to-element reference audit:

```bash
grafana-dashboard validate --input dashboard.v2.json --input-format resource
grafana-dashboard validate --input dashboard-spec.json --input-format spec
```

This is deterministic and offline once the binary is installed. It validates the canonical schema model but cannot reproduce every API-server admission rule, installed-plugin constraint, or client-side editor restriction.

Grafana's v2 code editor converts the served OpenAPI definitions into Draft-07 JSON Schema and applies several frontend-specific schema repairs before registering the result with Monaco. Run the separate editor compatibility check before pasting or applying JSON in that editor:

```bash
grafana-inspect editor-schema dashboard.v2.json --input-format resource
grafana-inspect editor-schema dashboard-spec.json --input-format spec
```

`grafana-inspect editor-schema` first runs canonical validation and the layout audit, then executes the pinned upstream schema converter and Monaco JSON worker. Keep it separate from `grafana-dashboard validate`: editor compatibility can be stricter than the canonical v2 contract. For example, the pinned Grafana editor rejects `null` threshold values as non-numeric even though the CUE contract defines `null` as the negative-infinity threshold. Treat such failures as compatibility errors for dashboards that must pass through the editor.

The authoritative check is Grafana's stable-v2 resource API with strict field validation and a dry run:

```bash
grafana-dashboard validate-live \
  --input dashboard.v2.json \
  --namespace default
```

The request is sent to:

```text
POST /apis/dashboard.grafana.app/v2/namespaces/<namespace>/dashboards?dryRun=All&fieldValidation=Strict
```

It does not persist the dashboard. Use a CA file when needed; reserve `--insecure-skip-tls-verify` for explicitly accepted test environments.

## Updating the Grafana pin

Pins and dependency updates belong to the dotfiles repository. Run `node tools/update-grafana.mjs --check` there to compare the installed source pins with the latest stable release, or omit `--check` to update the Go/npm dependencies and release manifest together. Review conversion fixtures, editor checks, and live integration before accepting an update. Do not pin an independent Grafana version in the skill.
