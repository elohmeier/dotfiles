from __future__ import annotations

import json
import re
import sys
import uuid
from typing import Any, cast
from urllib.parse import quote

import httpx
import rich_click as click

from .common import (
    _STEP_RE,
    _STEP_UNIT_MS,
    FOLDER_SEARCH_PAGE_SIZE,
    REQUEST_EXTENSIONS,
    SHOW_APP_RESOURCES,
    SHOW_FIXED_RESOURCES,
    SHOW_RESOURCE_ALIASES,
)


def parse_step_ms(s: str) -> int:
    m = _STEP_RE.match(s)
    if not m:
        raise click.UsageError(
            f"--step: bad duration {s!r} (expected e.g. 30s, 1m, 500ms)"
        )
    n, unit = int(m.group(1)), m.group(2)
    return n * _STEP_UNIT_MS[unit]


def cmd_list(c: httpx.Client, args: Any) -> int:
    r = c.get("/api/datasources", extensions=REQUEST_EXTENSIONS)
    r.raise_for_status()
    rows = r.json()
    if args.type:
        rows = [d for d in rows if d.get("type") == args.type]
    rows.sort(key=lambda d: (d.get("type", ""), d.get("name", "")))
    width_uid = max((len(d["uid"]) for d in rows), default=3)
    width_type = max((len(d["type"]) for d in rows), default=4)
    print(f"{'UID':<{width_uid}}  {'TYPE':<{width_type}}  NAME")
    for d in rows:
        default = " *" if d.get("isDefault") else ""
        print(
            f"{d['uid']:<{width_uid}}  {d['type']:<{width_type}}  {d['name']}{default}"
        )
    print(f"\n{len(rows)} datasource(s)")
    return 0


def load_target(path: str) -> dict:
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise click.UsageError("--target JSON must be a single target object")
    return obj


def ds_type_for(c: httpx.Client, uid: str) -> str:
    r = c.get(f"/api/datasources/uid/{uid}", extensions=REQUEST_EXTENSIONS)
    r.raise_for_status()
    return r.json()["type"]


def build_sql_target(uid: str, ds_type: str, sql: str) -> dict:
    return {
        "refId": "A",
        "datasource": {"uid": uid, "type": ds_type},
        "format": "table",
        "rawSql": sql,
    }


def build_lucene_target(
    uid: str, ds_type: str, query: str, agg: str, limit: int, time_field: str
) -> dict:
    t: dict[str, Any] = {
        "refId": "A",
        "datasource": {"uid": uid, "type": ds_type},
        "query": query,
        "queryType": "lucene",
        "timeField": time_field,
    }
    if agg == "count":
        t["metrics"] = [{"id": "1", "type": "count"}]
        t["bucketAggs"] = [
            {
                "id": "2",
                "type": "date_histogram",
                "field": time_field,
                "settings": {"interval": "auto"},
            }
        ]
    else:  # logs / raw docs
        t["metrics"] = [{"id": "1", "type": "logs", "settings": {"limit": str(limit)}}]
        t["bucketAggs"] = []
    return t


def cmd_metrics(c: httpx.Client, args: Any) -> int:
    params: list[tuple[str, str | int | float | None]] = []
    for m in args.match or []:
        params.append(("match[]", m))
    if args.start:
        params.append(("start", args.start))
    if args.end:
        params.append(("end", args.end))
    r = c.get(
        f"/api/datasources/proxy/uid/{args.uid}/api/v1/label/__name__/values",
        params=params,
        extensions=REQUEST_EXTENSIONS,
    )
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        return 1
    names: list[str] = r.json().get("data", [])
    if args.grep:
        rx = re.compile(args.grep)
        names = [n for n in names if rx.search(n)]
    total = len(names)
    if args.limit and args.limit > 0:
        names = names[: args.limit]
    for n in names:
        print(n)
    shown = len(names)
    suffix = f" (of {total})" if shown < total else ""
    print(f"\n{shown} metric(s){suffix}", file=sys.stderr)
    return 0


def cmd_alert_rules(c: httpx.Client, args: Any) -> int:
    if args.panel_id is not None and not args.dashboard_uid:
        raise click.UsageError("alert-rules: --panel-id requires --dashboard-uid")

    params: list[tuple[str, str | int | float | None]] = [
        (key, value)
        for key, values in (
            ("rule_group", args.group),
            ("rule_name", args.rule),
            ("rule_uid", args.uid),
            ("datasource_uid", args.datasource_uid),
            ("state", args.state),
            ("health", args.health),
            ("rule_matcher", args.label_matcher),
        )
        for value in values
    ]
    params.extend(
        (key, value)
        for key, value in (
            ("folder_uid", args.folder_uid),
            ("search.rule_name", args.title),
            ("search.rule_group", args.search_group),
            ("search.folder", args.search_folder),
            ("receiver_name", args.receiver),
            ("rule_type", args.rule_type),
            ("dashboard_uid", args.dashboard_uid),
            ("panel_id", args.panel_id),
            ("plugins", args.plugins),
            ("group_limit", args.group_limit),
            ("rule_limit", args.rule_limit),
            ("group_next_token", args.next_token),
            ("limit_alerts", args.limit_alerts),
        )
        if value is not None
    )
    r = c.get(
        "/api/prometheus/grafana/api/v1/rules",
        params=params,
        extensions=REQUEST_EXTENSIONS,
    )
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        return 1
    body = r.json()
    print(json.dumps(body, indent=2, ensure_ascii=False))
    return 0 if body.get("status") == "success" else 1


def cmd_show(c: httpx.Client, args: Any) -> int:
    resource = SHOW_RESOURCE_ALIASES.get(args.resource, args.resource)
    params: list[tuple[str, str | int | float | None]] = []
    if resource in SHOW_APP_RESOURCES:
        path = SHOW_APP_RESOURCES[resource].format(
            namespace=quote(args.namespace, safe="")
        )
        if args.name:
            path += f"/{quote(args.name, safe='')}"
        else:
            params.append(("limit", args.limit))
            for key, value in (
                ("continue", args.continue_token),
                ("fieldSelector", args.field_selector),
                ("labelSelector", args.label_selector),
            ):
                if value:
                    params.append((key, value))
    elif resource == "teams":
        if (
            args.name
            or args.continue_token
            or args.field_selector
            or args.label_selector
        ):
            raise click.UsageError("show teams: use --query, --page, and --limit")
        path = "/api/teams/search"
        params = [("page", args.page), ("perpage", args.limit)]
        if args.query:
            params.append(("query", args.query))
    elif resource == "folders":
        if (
            args.query
            or args.continue_token
            or args.field_selector
            or args.label_selector
        ):
            raise click.UsageError("show folders: use --name for a folder UID")
        path = "/api/folders"
        if args.name:
            path += f"/{quote(args.name, safe='')}"
        else:
            params = [("limit", args.limit)]
    else:
        if any(
            (
                args.name,
                args.query,
                args.continue_token,
                args.field_selector,
                args.label_selector,
            )
        ):
            raise click.UsageError(f"show {resource}: filters are not supported")
        path = SHOW_FIXED_RESOURCES[resource]

    r = c.get(path, params=params, extensions=REQUEST_EXTENSIONS)
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        return 1
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    return 0


def fetch_folder_search(c: httpx.Client, dashboards: bool) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    item_types = ["dash-folder"]
    if dashboards:
        item_types.append("dash-db")
    for item_type in item_types:
        page = 1
        while True:
            params: list[tuple[str, str | int | float | None]] = [
                ("type", item_type),
                ("limit", FOLDER_SEARCH_PAGE_SIZE),
                ("page", page),
            ]
            response = c.get(
                "/api/search",
                params=params,
                extensions=REQUEST_EXTENSIONS,
            )
            if response.status_code >= 400:
                raise click.ClickException(
                    f"Grafana folder search failed with HTTP "
                    f"{response.status_code}: {response.text}"
                )
            page_items = response.json()
            if not isinstance(page_items, list):
                raise click.ClickException("Grafana folder search returned a non-list")
            items.extend(item for item in page_items if isinstance(item, dict))
            if len(page_items) < FOLDER_SEARCH_PAGE_SIZE:
                break
            page += 1
    return items


def build_folder_tree(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {
        item["uid"]: {
            "uid": item["uid"],
            "title": item.get("title", item["uid"]),
            "url": item.get("url"),
            "parentUid": item.get("folderUid"),
            "children": [],
            "dashboards": [],
        }
        for item in items
        if item.get("type") == "dash-folder" and isinstance(item.get("uid"), str)
    }
    roots: list[dict[str, Any]] = []
    for node in nodes.values():
        parent = nodes.get(node["parentUid"])
        if parent:
            cast(list[dict[str, Any]], parent["children"]).append(node)
        else:
            roots.append(node)

    root_dashboards: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") != "dash-db" or not isinstance(item.get("uid"), str):
            continue
        dashboard = {
            "uid": item["uid"],
            "title": item.get("title", item["uid"]),
            "url": item.get("url"),
            "tags": item.get("tags", []),
        }
        parent_uid = item.get("folderUid")
        parent = nodes.get(parent_uid) if isinstance(parent_uid, str) else None
        if parent:
            cast(list[dict[str, Any]], parent["dashboards"]).append(dashboard)
        else:
            root_dashboards.append(dashboard)

    def sort_node(node: dict[str, Any]) -> None:
        node["children"].sort(key=lambda child: child["title"].casefold())
        node["dashboards"].sort(key=lambda item: item["title"].casefold())
        for child in node["children"]:
            sort_node(child)

    roots.sort(key=lambda node: node["title"].casefold())
    root_dashboards.sort(key=lambda item: item["title"].casefold())
    for root in roots:
        sort_node(root)
    return roots, root_dashboards, nodes


def export_folder_node(node: dict[str, Any], depth: int | None) -> dict[str, Any]:
    next_depth = None if depth is None else depth - 1
    children = (
        [export_folder_node(child, next_depth) for child in node["children"]]
        if depth is None or depth > 0
        else []
    )
    return {
        "uid": node["uid"],
        "title": node["title"],
        "url": node["url"],
        "parentUid": node["parentUid"],
        "children": children,
        "dashboards": node["dashboards"],
    }


def render_folder_node(
    node: dict[str, Any],
    depth: int | None,
    prefix: str = "",
    connector: str = "",
) -> list[str]:
    lines = [f"{prefix}{connector}{node['title']} [{node['uid']}]"]
    children = node["children"] if depth is None or depth > 0 else []
    entries = [("folder", child) for child in children] + [
        ("dashboard", dashboard) for dashboard in node["dashboards"]
    ]
    next_depth = None if depth is None else depth - 1
    child_prefix = prefix + (
        "    " if connector == "└── " else "│   " if connector else ""
    )
    for index, (kind, item) in enumerate(entries):
        last = index == len(entries) - 1
        branch = "└── " if last else "├── "
        if kind == "folder":
            lines.extend(render_folder_node(item, next_depth, child_prefix, branch))
        else:
            lines.append(
                f"{child_prefix}{branch}dashboard: {item['title']} [{item['uid']}]"
            )
    return lines


def cmd_folders(c: httpx.Client, args: Any) -> int:
    roots, root_dashboards, nodes = build_folder_tree(
        fetch_folder_search(c, args.dashboards)
    )
    if args.uid:
        root = nodes.get(args.uid)
        if root is None:
            raise click.ClickException(f"folder UID {args.uid!r} was not found")
        roots = [root]
        root_dashboards = []

    if args.json_output:
        print(
            json.dumps(
                {
                    "folders": [export_folder_node(root, args.depth) for root in roots],
                    "dashboards": root_dashboards,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    lines = [line for root in roots for line in render_folder_node(root, args.depth)]
    if root_dashboards:
        lines.append("General")
        for index, item in enumerate(root_dashboards):
            branch = "└── " if index == len(root_dashboards) - 1 else "├── "
            lines.append(f"{branch}dashboard: {item['title']} [{item['uid']}]")
    print("\n".join(lines) if lines else "No folders found.")
    return 0


def cmd_query(c: httpx.Client, args: Any) -> int:
    modes = sum(bool(x) for x in (args.target, args.expr, args.sql, args.lucene))
    if modes != 1:
        raise click.UsageError(
            "query: pick exactly one of --target / --expr / --sql / --lucene"
        )

    if args.target:
        query = load_target(args.target)
        if args.uid:
            ds = query.setdefault("datasource", {})
            ds["uid"] = args.uid
            ds.setdefault("type", "")
        query.setdefault("refId", "A")
        if "datasource" not in query or "uid" not in query["datasource"]:
            raise click.UsageError(
                "target missing datasource.uid; pass --uid to override"
            )
    else:
        if not args.uid:
            raise click.UsageError(
                "query: --uid is required with --expr/--sql/--lucene"
            )
        ds_type = ds_type_for(c, args.uid)
        if args.expr:
            query = {
                "refId": "A",
                "datasource": {"uid": args.uid, "type": ds_type},
                "expr": args.expr,
            }
            if ds_type in ("prometheus", "loki"):
                query["range"] = not args.instant
                query["instant"] = args.instant
                if args.step:
                    query["intervalMs"] = parse_step_ms(args.step)
                    query["maxDataPoints"] = 1_000_000
        elif args.sql:
            query = build_sql_target(args.uid, ds_type, args.sql)
        else:
            query = build_lucene_target(
                args.uid, ds_type, args.lucene, args.agg, args.limit, args.time_field
            )

    body = {"queries": [query], "from": args.start, "to": args.end}

    r = c.post(
        "/api/ds/query",
        json=body,
        params={"requestId": uuid.uuid4().hex},
        extensions=REQUEST_EXTENSIONS,
    )
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        return 1
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    return 0
