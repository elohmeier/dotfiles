# Generated Dashboard Management

Use this when users ask about Jsonnet, dashboards-as-code, GitOps dashboards, generated dashboards, edit locks, provenance, or whether a dashboard can be marked as managed by a plugin/app.

## Source Of Truth

Treat Jsonnet or another generator input as the source of truth outside the dashboard spec. Compile it to classic dashboard JSON or a `dashboard.grafana.app` resource, and store the source in git, object storage, or a companion system.

When the source is classic JSON but the generator patches stable v2, convert the baseline first with `grafana-dashboard render`. The Jsonnet program should read `std.extVar('grafanaDashboardV2')`; it must not contain a handwritten classic-to-v2 converter. For new dashboards, author stable v2 directly with the thin constructors in `assets/dashboard/v2.libsonnet`. See `dashboard-v2-tooling.md` for the exact boundary and validation commands.

Do not recommend a custom top-level dashboard field for full Jsonnet source or generator state if the user needs normal Grafana UI round trips. Legacy dashboard storage can physically keep arbitrary JSON in `Dashboard.Data`, but the frontend save path rebuilds the save model from known `DashboardModel` fields, so unknown fields can be dropped after edit/save/export/migration. V2 dashboard specs are also explicit; custom state belongs in resource metadata, not `spec`.

If the user asks to preserve a small amount of generator state, prefer metadata annotations for provenance and keep the full source elsewhere.

## Provenance Metadata

For unified/k8s dashboard resources, use `metadata.annotations` for source and manager identity:

```yaml
metadata:
  annotations:
    grafana.app/managedBy: plugin
    grafana.app/managerId: my-app-plugin
    grafana.app/sourcePath: dashboards/service.jsonnet
    grafana.app/sourceChecksum: 8f3c1e2
```

Common manager/source annotations:

- `grafana.app/managedBy`: known values include `repo`, `terraform`, `kubectl`, `plugin`, `grafana`, and `classic-file-provisioning`.
- `grafana.app/managerId`: required for backend manager recognition. Set this to the repo name, plugin ID, Terraform workspace/provider identity, or other stable manager identity.
- `grafana.app/managerAllowsEdits`: set to string `"true"` only when UI edits are allowed by the ownership model.
- `grafana.app/sourcePath`: source path, URL, or logical generator entrypoint.
- `grafana.app/sourceChecksum`: git SHA, content hash, or generator checksum.
- `grafana.app/sourceTimestamp`: optional Unix-millis source timestamp.

Use labels only for small selection/indexing values. Do not store large Jsonnet blobs in labels or annotations.

## Edit Behavior

`editable: false` is a soft dashboard setting, not a robust source-of-truth guard. Users with save permission may still get a "make editable" path in the UI.

For generated dashboards, prefer managed-resource semantics:

- Non-repo managed dashboards are treated as not directly editable in the scenes UI unless `grafana.app/managerAllowsEdits: "true"` is present.
- Repo-managed dashboards are a special case in provisioning flows and may stay editable depending on feature toggles and repository UX.
- If UI edits should detach the dashboard from Jsonnet, make that explicit: warn the user, remove manager/source annotations on save, and save the dashboard as user-managed.
- If UI edits should be overwritten on the next sync, say that plainly and keep the manager/source metadata.

For a warning-only workflow, compare current dashboard generation provenance with metadata before save. If the generator checksum/source is stale or missing, warn that saving from the UI detaches or invalidates generated provenance.

## Plugin/App-Managed Dashboards

Grafana can mark a dashboard as managed by an app/plugin:

```yaml
metadata:
  annotations:
    grafana.app/managedBy: plugin
    grafana.app/managerId: my-app-plugin
```

Set both annotations. Backend manager accessors ignore manager metadata without `managerId`, while the UI may still see `managedBy` and treat the dashboard as managed.

Internal plugin dashboard import/update paths also model this:

- `ImportDashboardRequest.PluginId` flows through `SaveDashboardCommand.PluginID`.
- `SetPluginIDMeta` stamps `managedBy=plugin` and `managerId=<pluginID>`.
- `GetDashboardsByPluginID` searches dashboards by `managedBy=plugin` and `managerId=<pluginID>`.

The legacy public `/api/dashboards/db` save shape does not let callers pass `PluginID` or resource metadata directly. Use the unified/k8s dashboard resource API with metadata annotations, or an internal/backend path that sets `PluginID`.

## Practical Recommendation

For Jsonnet-generated dashboards managed by an app/plugin:

1. Compile Jsonnet to a dashboard resource.
2. Save the resource with `managedBy=plugin`, `managerId=<app-plugin-id>`, `sourcePath`, and `sourceChecksum`.
3. Keep the Jsonnet source outside Grafana.
4. Decide whether UI edits are blocked, allowed with `managerAllowsEdits`, or allowed only through an explicit detach/copy flow.
5. Verify by saving through the intended API path, reloading the dashboard, editing in the UI if applicable, and checking that metadata behaves as expected.
