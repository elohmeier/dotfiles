from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx
import rich_click as click

from .alerts import (
    json_content,
    load_document,
    mutate_alert_rule,
    prepare_alert_rule_patch,
    print_response,
)
from .common import ALERT_RULE_PATCH_CONTENT_TYPES, REQUEST_EXTENSIONS


def dashboard_path(namespace: str, name: str | None = None) -> str:
    path = f"/apis/dashboard.grafana.app/v2/namespaces/{quote(namespace, safe='')}/dashboards"
    return f"{path}/{quote(name, safe='')}" if name else path


def fetch_dashboard(
    c: httpx.Client, namespace: str, name: str
) -> tuple[dict[str, Any] | None, int]:
    response = c.get(dashboard_path(namespace, name), extensions=REQUEST_EXTENSIONS)
    if response.status_code == 404:
        return None, 0
    if response.status_code >= 400:
        return None, print_response(response)
    dashboard = response.json()
    if not isinstance(dashboard, dict):
        raise click.ClickException("Grafana returned a non-object dashboard")
    return dashboard, 0


def upload_source(
    source: Any, uid: str | None
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(source, dict):
        raise click.UsageError("dashboard file must contain a JSON object")
    if source.get("apiVersion") == "dashboard.grafana.app/v2":
        if source.get("kind") != "Dashboard":
            raise click.UsageError("dashboard resource must have kind Dashboard")
        metadata = source.get("metadata")
        spec = source.get("spec")
        name = metadata.get("name") if isinstance(metadata, dict) else None
    else:
        metadata = {}
        spec = source
        name = uid
    if not isinstance(name, str) or not name:
        raise click.UsageError(
            "dashboard UID is required (--uid for an unwrapped spec)"
        )
    if uid and uid != name:
        raise click.UsageError("--uid does not match metadata.name")
    if (
        not isinstance(spec, dict)
        or not isinstance(spec.get("title"), str)
        or not isinstance(spec.get("elements"), dict)
        or "layout" not in spec
    ):
        raise click.UsageError("dashboard spec needs title, elements, and layout")
    return name, spec, metadata


def cmd_dashboard_get(c: httpx.Client, args: Any) -> int:
    dashboard, result = fetch_dashboard(c, args.namespace, args.uid)
    if dashboard is None:
        if result == 0:
            raise click.ClickException(f"dashboard {args.uid} does not exist")
        return result
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))
    return 0


def cmd_dashboard_upload(c: httpx.Client, args: Any) -> int:
    name, spec, source_metadata = upload_source(load_document(args.file), args.uid)
    current, result = fetch_dashboard(c, args.namespace, name)
    if result:
        return result
    if current is None:
        metadata: dict[str, Any] = {"name": name}
        annotations = source_metadata.get("annotations", {})
        if isinstance(annotations, dict):
            metadata["annotations"] = annotations.copy()
        if args.folder_uid:
            metadata.setdefault("annotations", {})["grafana.app/folder"] = (
                args.folder_uid
            )
        method, path, action = "POST", dashboard_path(args.namespace), "Create"
    else:
        metadata = current["metadata"]
        if args.folder_uid:
            raise click.UsageError(
                "--folder-uid is supported only when creating a dashboard"
            )
        method, path, action = "PUT", dashboard_path(args.namespace, name), "Update"
        if current.get("spec") == spec:
            click.echo("No changes.", err=True)
            return 0
    dashboard = {
        "apiVersion": "dashboard.grafana.app/v2",
        "kind": "Dashboard",
        "metadata": metadata,
        "spec": spec,
    }
    return mutate_alert_rule(
        c,
        method,
        path,
        json_content(dashboard),
        "application/json",
        f"{action} dashboard {name}?",
        args.dry_run,
        args.yes,
    )


def cmd_dashboard_patch(c: httpx.Client, args: Any) -> int:
    current, result = fetch_dashboard(c, args.namespace, args.uid)
    if current is None:
        if result == 0:
            raise click.ClickException(f"dashboard {args.uid} does not exist")
        return result
    content = prepare_alert_rule_patch(
        load_document(args.file), args.patch_type, args.namespace, args.uid, current
    )
    return mutate_alert_rule(
        c,
        "PATCH",
        dashboard_path(args.namespace, args.uid),
        content,
        ALERT_RULE_PATCH_CONTENT_TYPES[args.patch_type],
        f"Patch dashboard {args.uid}?",
        args.dry_run,
        args.yes,
    )
