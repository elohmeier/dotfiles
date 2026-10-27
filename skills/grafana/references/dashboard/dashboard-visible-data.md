# Dashboard data and editor checks

The dotfiles repository installs `grafana-inspect` on PATH. Its Go companion, `grafana-dashboard`, performs canonical v2 validation and strict live dry runs. Run `grafana-inspect version` to see the exact stable Grafana target. The skill contains no executable runtime or dependencies.

## Offline structure

```bash
grafana-inspect structure dashboards/service-red.json
grafana-inspect structure dashboards/service-red.json --format json
```

This reads classic dashboard JSON or stable-v2 resources/specs and reports metadata, variables, annotations, layout, panels, and queries. It does not query Grafana.

## Live data

Supply `GRAFANA_URL` and `GRAFANA_TOKEN` through the shell or `mise exec`. Basic authentication uses `GRAFANA_USERNAME` and `GRAFANA_PASSWORD`. The tool does not parse `.env` or `mise.toml` itself.

```bash
grafana-inspect data dashboards/service-red.json --list-panels
grafana-inspect data dashboards/service-red.json --panel-id 3 --from now-30m --to now --var service=checkout
grafana-inspect data dashboards/service-red.json --panel-ids 2,3,4 --format json --output .tmp/visible-data.json
```

Use `--raw-frames` to inspect datasource output before transformations, `--step 30s` to control query interval, and bounded panel/time/variable selections to limit load. See `grafana-inspect data --help` for concurrency, timeout, collapsed-row, and hidden-target options.

The data pipeline calls `@grafana/data` transformations, field overrides, formatting, and reducers. It does not repair joins, invent label fields, or replace aggregations. Unsupported transformations and processing failures fail the check; failed processing does not report raw frames as successful visible output. Raw datasource frames remain available through the explicit raw-frame mode.

For inventory tables, apply `labelsToFields` in the dashboard when required, prepare fields per refId, then join. Check one and multiple returned series: merge can change frame refIds. See [queries-and-transformations.md](queries-and-transformations.md#multi-metric-prometheus-inventory-tables).

Variables use saved values and explicit `--var` overrides; variable queries are not executed. Panel plugins, datasource frontend processing, browser layout, tab selection, section-variable scope, repeats, and conditional rendering are not fully emulated. Use browser review when those behaviors matter.

## Editor checks

Schema compatibility executes Grafana's own schema conversion and Monaco JSON worker, after canonical validation:

```bash
grafana-inspect editor-schema dashboards/service-red.json
grafana-inspect editor-schema dashboard-spec.json --input-format spec
```

Transformation diagnostics mount the pinned upstream transformation rows and editors under jsdom:

```bash
grafana-inspect editor-diagnostics dashboards/service-red.json --panel-id 8
grafana-inspect editor-diagnostics dashboards/service-red.json --panel-id 8 --format json
```

These commands lazily download/cache the exact pinned Grafana source and install its locked frontend dependencies. No endpoint is needed. `--grafana-source` accepts a clean checkout of that exact commit with frontend dependencies installed.

Transformation diagnostics use one synthetic frame per query. They collect actual editor alerts without maintaining warning-message rules. `--report-only` reports alerts without failing for them; unknown transformation registrations still fail. A quiet editor for synthetic input does not establish correctness for every live frame shape.

## Connection and result contract

`GRAFANA_TLS_VERIFY` defaults to true, including with `GRAFANA_RESOLVE` DNS overrides. `GRAFANA_CA_FILE` supplies a CA bundle; `GRAFANA_HOST_HEADER` and `GRAFANA_SNI_HOSTNAME` override virtual-host routing where necessary. Disabling certificate verification requires an explicit setting.

Data and editor commands return 0 for success, 1 for query/processing/validation diagnostics, and 2 for invocation/runtime failures. Review zero versus no-data, stale/partial data, field names, units, mappings, sorting, row/series counts, and transformation output as well as the exit code. Schema, frame, and editor checks complement browser validation of the actual dashboard.
