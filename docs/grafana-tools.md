# Grafana tools

This repository owns the tools, tests, dependencies, and stable Grafana pin. The separate `elohmeier/skills` repository owns Grafana guidance and examples, and invokes these commands on PATH.

| Command             | Purpose                                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `grafana-query`     | Datasource queries, API resources, alert management, and local API proxies                                         |
| `grafana-users`     | Server-wide user administration using administrator Basic authentication                                           |
| `grafana-dashboard` | Upstream Go conversion, CUE validation, context export, Jsonnet rendering, and strict live dry runs                |
| `grafana-inspect`   | Offline structure, live frame processing, upstream editor-schema validation, and transformation-editor diagnostics |

Python commands are installed through `pyproject.toml` and `home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl`. The Go/Node commands use `home/.chezmoiscripts/run_onchange_after_install-grafana-tools.sh.tmpl`; the Node runtime lives in `~/.local/share/ennos-dotfiles/grafana-inspect`. Go and Node are included in the base package hook. The launcher preserves the current working directory.

```sh
grafana-inspect structure dashboard.json
grafana-dashboard validate --input dashboard.json --input-format resource
grafana-inspect editor-schema dashboard.json
grafana-inspect data dashboard.json --panel-id 3 --from now-30m --var service=checkout
grafana-inspect editor-diagnostics dashboard.json --panel-id 3
grafana-dashboard validate-live --input dashboard.json --namespace default
```

Run each command with `--help` for options. `grafana-dashboard render` additionally needs `jsonnet`. `editor-schema` and `editor-diagnostics` lazily download the pinned Grafana source into `~/.cache/grafana-tools` (or `$XDG_CACHE_HOME/grafana-tools`) and install its locked frontend dependencies using the private Corepack dependency. Other commands do not need that checkout. A `--grafana-source` override must be a clean checkout of the pinned commit with its dependencies installed.

## Configuration and semantics

Use `GRAFANA_URL` and `GRAFANA_TOKEN`, or `GRAFANA_USERNAME`/`GRAFANA_PASSWORD`. Server administration requires administrator credentials. TLS verification defaults to true; use `GRAFANA_CA_FILE` for a CA bundle and `GRAFANA_TLS_VERIFY` for an explicit verification setting. `GRAFANA_HOST_HEADER` and `GRAFANA_SNI_HOSTNAME` handle virtual-host routing. Go and Node additionally accept `GRAFANA_RESOLVE` DNS overrides. Supply environment variables through the shell or `mise exec`; the tools do not parse project environment files themselves.

Canonical validation uses upstream Go types and CUE. Editor-schema validation uses the actual upstream schema converter and Monaco JSON worker. Transformation diagnostics use upstream React editors with synthetic frames. Data inspection executes `@grafana/data` transformations and fails on unsupported transformations or processing errors. It does not rewrite the dashboard's joins or aggregations.

Data inspection is not a browser renderer: variable queries, datasource frontend processing, panel plugin UI, repeats, section-scoped variables, conditional rendering, and selected-tab visibility are not fully emulated. Use bounded panel selections and explicit variable values. Use browser checks when those behaviors matter.

Grouped alert creation intentionally retains the provisioning API: integration against 13.2.2 confirmed that app-resource creation rejects setting a rule group. The Python converter preserves that existing capability. Mutation confirmations, managed-resource protections, and the distinction between local-only alert dry runs and server dashboard dry runs remain intact.

The old `grafana-dashboard-viewer`, skill-local `dashboard-v2`, and direct TypeScript script interfaces have been removed. Use `grafana-inspect structure`, `grafana-dashboard`, and the appropriate `grafana-inspect` subcommand instead. Go `validate-editor` is replaced by `grafana-inspect editor-schema FILE`.

## Stable release updates

`tools/grafana-version.json` selects the release/commit. Go submodules, npm packages, Python version reporting, and the advanced editor runtime track that selection together. Installation uses committed dependencies and lockfiles.

```sh
node tools/update-grafana.mjs --check          # compare against latest stable
node tools/update-grafana.mjs --check --offline # check local pin consistency
node tools/update-grafana.mjs                  # update pins, locks, and run basic checks
```

Before accepting an update, run the tests below, review conversion changes, validate skill examples, and exercise context export, strict dashboard dry runs, grouped alert creation, and data queries against a disposable matching Grafana instance. Never substitute a prerelease checkout or mix frontend/backend releases.

## Validation

```sh
uv run pytest -q tests/test_grafana_query.py tests/test_grafana_users.py
uv run ruff format scripts/grafana
uv run ruff check scripts/grafana
uv run ty check scripts/grafana
(cd tools/grafana-dashboard && go test ./...)
npm --prefix tools/grafana-inspect ci
npm --prefix tools/grafana-inspect test
npm --prefix tools/grafana-inspect run typecheck
npm --prefix tools/grafana-inspect run build
# Requires the matching grafana-dashboard on PATH; may bootstrap the editor runtime:
npm --prefix tools/grafana-inspect run test:editor
```

The regression fixtures live with the tools and do not require a skill checkout. The Node integration test distinguishes canonical acceptance of null thresholds from the editor's rejection, using the actual pinned editor pipeline.
