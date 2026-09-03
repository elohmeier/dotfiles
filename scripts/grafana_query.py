"""Query Grafana datasources and alerting resources, with local API facades."""

from __future__ import annotations

import copy
import contextlib
from collections import Counter, deque
from dataclasses import dataclass, field
import difflib
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import re
import sys
import threading
import time
from urllib.parse import quote, unquote, urlsplit
import uuid
from types import SimpleNamespace
from typing import Any, cast

import httpx
import rich_click as click
import yaml
from click.exceptions import Exit
from rich import box
from rich.console import Console, Group
from rich.filesize import decimal as format_bytes
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_STEP_RE = re.compile(r"^\s*(\d+)\s*(ms|s|m|h)?\s*$")
_STEP_UNIT_MS = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000, None: 1000}


def parse_step_ms(s: str) -> int:
    m = _STEP_RE.match(s)
    if not m:
        raise click.UsageError(
            f"--step: bad duration {s!r} (expected e.g. 30s, 1m, 500ms)"
        )
    n, unit = int(m.group(1)), m.group(2)
    return n * _STEP_UNIT_MS[unit]


REQUEST_EXTENSIONS: dict[str, str] = {}
CLIENT_DISCONNECT_ERRNOS = {
    errno.ECONNABORTED,
    errno.ECONNRESET,
    errno.EPIPE,
}
DEFAULT_QUERY_API_MAX_BODY_BYTES = 4 * 1024 * 1024
FOLDER_SEARCH_PAGE_SIZE = 1000
ELASTICSEARCH_POST_READ_SUFFIXES = frozenset(
    {
        "/_count",
        "/_field_caps",
        "/_mget",
        "/_msearch",
        "/_render/template",
        "/_search",
        "/_search/template",
        "/_terms_enum",
        "/_validate/query",
    }
)
SHOW_APP_RESOURCES = {
    "alert-rules": "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/alertrules",
    "contact-points": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/receivers",
    "inhibition-rules": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/inhibitionrules",
    "mute-timings": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/timeintervals",
    "notification-policies": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/routingtrees",
    "recording-rules": "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/recordingrules",
    "rule-sequences": "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/rulesequences",
    "templates": "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{namespace}/templategroups",
}
SHOW_FIXED_RESOURCES = {
    "active-alerts": "/api/alertmanager/grafana/api/v2/alerts",
    "contact-point-status": "/api/alertmanager/grafana/config/api/v1/receivers",
    "silences": "/api/alertmanager/grafana/api/v2/silences",
}
SHOW_RESOURCE_ALIASES = {
    "endpoints": "contact-points",
    "notification-rules": "notification-policies",
}
ALERT_RULE_API_VERSION = "rules.alerting.grafana.app/v0alpha1"
ALERT_RULE_KIND = "AlertRule"
ALERT_RULES_APP_PATH = (
    "/apis/rules.alerting.grafana.app/v0alpha1/namespaces/{namespace}/alertrules"
)
ALERT_RULE_PROVISIONING_PATH = "/api/v1/provisioning/alert-rules"
ALERT_RULE_FOLDER_KEY = "grafana.app/folder"
ALERT_RULE_GROUP_KEY = "grafana.com/group"
ALERT_RULE_PATCH_CONTENT_TYPES = {
    "apply": "application/apply-patch+yaml",
    "json": "application/json-patch+json",
    "merge": "application/merge-patch+json",
}
ALERT_RULE_MANAGER_ANNOTATIONS = frozenset(
    {
        "grafana.app/managedBy",
        "grafana.app/managerAllowsEdits",
        "grafana.app/managerId",
        "grafana.app/managerSuspended",
        "grafana.com/provenance",
    }
)
ALERT_RULE_SERVER_METADATA_FIELDS = frozenset(
    {
        "creationTimestamp",
        "deletionGracePeriodSeconds",
        "deletionTimestamp",
        "generation",
        "managedFields",
        "selfLink",
        "uid",
    }
)
ALERT_RULE_SERVER_ANNOTATIONS = frozenset(
    {
        "grafana.app/createdBy",
        "grafana.app/updatedBy",
        "grafana.app/updatedTimestamp",
        "grafana.com/updatedBy",
        "grafana.com/updateTimestamp",
    }
)
ELASTICSEARCH_EXPLORE_LINK_START = (
    "{{/* grafana-query:elasticsearch-explore-link:v1:start */}}"
)
ELASTICSEARCH_EXPLORE_LINK_END = (
    "{{/* grafana-query:elasticsearch-explore-link:v1:end */}}"
)
ELASTICSEARCH_EXPLORE_LINK_LABEL = "Logs (letzte 30 Minuten):"
ELASTICSEARCH_EXPLORE_LINK_RE = re.compile(
    re.escape(ELASTICSEARCH_EXPLORE_LINK_START)
    + ".*?"
    + re.escape(ELASTICSEARCH_EXPLORE_LINK_END),
    re.DOTALL,
)
ELASTICSEARCH_LEGACY_EXPLORE_LINK_RE = re.compile(
    rf"^{re.escape(ELASTICSEARCH_EXPLORE_LINK_LABEL)} .*explore\?[^\n]*(?:\n|$)",
    re.MULTILINE,
)
ELASTICSEARCH_EXPLORE_QUERY_SENTINEL = "grafana-query-runtime-query"
SHOW_RESOURCES = tuple(
    sorted(
        SHOW_APP_RESOURCES.keys()
        | SHOW_FIXED_RESOURCES.keys()
        | SHOW_RESOURCE_ALIASES.keys()
        | {"folders", "teams"}
    )
)
console = Console(stderr=True)


@dataclass(slots=True, frozen=True)
class ElasticsearchAlertQuery:
    ref_id: str
    datasource_uid: str
    model: dict[str, Any]
    term_fields: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class ExploreLinkChange:
    name: str
    title: str
    rule: dict[str, Any]
    query: ElasticsearchAlertQuery
    description: str


@dataclass(slots=True)
class RequestSample:
    method: str
    route: str
    request_bytes: int
    started: float = field(default_factory=time.monotonic)
    when: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    status: int | None = None
    response_bytes: int = 0
    duration: float = 0
    upstream_duration: float | None = None
    disconnected: bool = False
    datasources: Counter[str] = field(default_factory=Counter)
    datasource_types: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DatasourceUsage:
    uid: str
    datasource_type: str = ""
    requests: int = 0
    targets: int = 0
    failed: int = 0
    last_seen: float = 0


@dataclass(slots=True, frozen=True)
class DatasourceSnapshot:
    uid: str
    datasource_type: str
    requests: int
    targets: int
    failed: int
    last_seen_age: float | None


@dataclass(slots=True, frozen=True)
class ProxyStatsSnapshot:
    uptime: float
    requests: int
    upstream_requests: int
    active_requests: int
    request_rate: float
    status_counts: dict[str, int]
    request_bytes: int
    response_bytes: int
    largest_response: int
    latencies: tuple[float, ...]
    upstream_latencies: tuple[float, ...]
    datasources: tuple[DatasourceSnapshot, ...]
    recent: tuple[RequestSample, ...]


class ProxyStats:
    def __init__(self, datasource_types: dict[str, str]) -> None:
        self.started = time.monotonic()
        self._lock = threading.Lock()
        self._requests = 0
        self._upstream_requests = 0
        self._active_requests = 0
        self._status_counts: Counter[str] = Counter()
        self._request_bytes = 0
        self._response_bytes = 0
        self._largest_response = 0
        self._request_times: deque[float] = deque()
        self._latencies: deque[float] = deque(maxlen=512)
        self._upstream_latencies: deque[float] = deque(maxlen=512)
        self._recent: deque[RequestSample] = deque(maxlen=8)
        self._datasources = {
            uid: DatasourceUsage(uid, datasource_type)
            for uid, datasource_type in datasource_types.items()
        }

    def begin(self, sample: RequestSample) -> None:
        with self._lock:
            self._requests += 1
            self._active_requests += 1
            self._request_times.append(sample.started)

    def finish(self, sample: RequestSample) -> None:
        with self._lock:
            self._active_requests -= 1
            bucket = (
                "disconnect"
                if sample.disconnected
                else f"{sample.status // 100}xx"
                if sample.status is not None
                else "error"
            )
            self._status_counts[bucket] += 1
            self._request_bytes += sample.request_bytes
            self._response_bytes += sample.response_bytes
            self._largest_response = max(self._largest_response, sample.response_bytes)
            self._latencies.append(sample.duration)
            if sample.upstream_duration is not None:
                self._upstream_requests += 1
                self._upstream_latencies.append(sample.upstream_duration)
                for uid, targets in sample.datasources.items():
                    usage = self._datasources.setdefault(uid, DatasourceUsage(uid))
                    usage.datasource_type = (
                        usage.datasource_type
                        or sample.datasource_types.get(uid, "unknown")
                    )
                    usage.requests += 1
                    usage.targets += targets
                    usage.failed += (
                        sample.disconnected
                        or sample.status is None
                        or sample.status >= 400
                    )
                    usage.last_seen = sample.started + sample.duration
            self._recent.append(sample)

    def snapshot(self) -> ProxyStatsSnapshot:
        now = time.monotonic()
        with self._lock:
            while self._request_times and self._request_times[0] < now - 60:
                self._request_times.popleft()
            uptime = now - self.started
            rate = len(self._request_times) / max(1, min(uptime, 60))
            datasources = tuple(
                DatasourceSnapshot(
                    usage.uid,
                    usage.datasource_type or "unknown",
                    usage.requests,
                    usage.targets,
                    usage.failed,
                    max(0, now - usage.last_seen) if usage.last_seen else None,
                )
                for usage in sorted(
                    self._datasources.values(),
                    key=lambda usage: (-usage.requests, usage.uid),
                )
            )
            return ProxyStatsSnapshot(
                uptime=uptime,
                requests=self._requests,
                upstream_requests=self._upstream_requests,
                active_requests=self._active_requests,
                request_rate=rate,
                status_counts=dict(self._status_counts),
                request_bytes=self._request_bytes,
                response_bytes=self._response_bytes,
                largest_response=self._largest_response,
                latencies=tuple(self._latencies),
                upstream_latencies=tuple(self._upstream_latencies),
                datasources=datasources,
                recent=tuple(reversed(self._recent)),
            )


def percentile(values: tuple[float, ...], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def format_latency(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def render_dashboard(
    stats: ProxyStats,
    title: str,
    endpoint: str,
    exposed: bool,
    width: int = 120,
) -> Group:
    snapshot = stats.snapshot()
    summary = Table.grid(expand=True)
    summary.add_row(
        Text.assemble(
            ("Requests ", "bold"),
            f"{snapshot.requests:,}",
            "   ",
            ("Upstream ", "bold"),
            f"{snapshot.upstream_requests:,}",
            "   ",
            ("Active ", "bold"),
            f"{snapshot.active_requests:,}",
            "   ",
            ("Rate (60s) ", "bold"),
            f"{snapshot.request_rate:.1f}/s",
        )
    )
    summary.add_row(
        Text.assemble(
            ("Status ", "bold"),
            (f"2xx {snapshot.status_counts.get('2xx', 0):,}", "green"),
            "   ",
            (f"3xx {snapshot.status_counts.get('3xx', 0):,}", "cyan"),
            "   ",
            (f"4xx {snapshot.status_counts.get('4xx', 0):,}", "yellow"),
            "   ",
            (f"5xx {snapshot.status_counts.get('5xx', 0):,}", "red"),
            "   ",
            ("Disconnects ", "bold"),
            f"{snapshot.status_counts.get('disconnect', 0):,}",
            "   ",
            ("Internal ", "bold"),
            f"{snapshot.status_counts.get('error', 0):,}",
        )
    )
    summary.add_row(
        Text.assemble(
            ("Latency (last 512) ", "bold"),
            f"p50 {format_latency(percentile(snapshot.latencies, 0.5))}",
            "   ",
            f"p95 {format_latency(percentile(snapshot.latencies, 0.95))}",
            "   ",
            ("Upstream p95 ", "bold"),
            format_latency(percentile(snapshot.upstream_latencies, 0.95)),
        )
    )
    summary.add_row(
        Text.assemble(
            ("Body traffic ", "bold"),
            f"in {format_bytes(snapshot.request_bytes)}",
            "   ",
            f"out {format_bytes(snapshot.response_bytes)}",
            "   ",
            ("Largest response ", "bold"),
            format_bytes(snapshot.largest_response),
        )
    )
    if exposed:
        summary.add_row(
            Text(
                "Warning: reachable beyond loopback; restrict access with a firewall or private network.",
                style="yellow bold",
            )
        )

    header = Text.assemble(
        (title, "bold"),
        " · ",
        endpoint,
        " · up ",
        format_elapsed(snapshot.uptime),
    )
    overview = Panel(summary, title=header, border_style="cyan", padding=(0, 1))

    datasource_table = Table(
        title="Datasource usage · since start",
        box=box.SIMPLE,
        expand=True,
        padding=(0, 1),
    )
    datasource_table.add_column("UID", ratio=3, overflow="ellipsis")
    datasource_table.add_column("Type", ratio=2, overflow="ellipsis")
    datasource_table.add_column("Requests", justify="right")
    datasource_table.add_column("Targets", justify="right")
    datasource_table.add_column("Failed", justify="right")
    datasource_table.add_column("Last", justify="right")
    for usage in snapshot.datasources[:10]:
        datasource_table.add_row(
            Text(usage.uid),
            Text(usage.datasource_type),
            f"{usage.requests:,}",
            f"{usage.targets:,}",
            Text(
                f"{usage.failed:,}",
                style="red" if usage.failed else "green",
            ),
            "—" if usage.last_seen_age is None else format_elapsed(usage.last_seen_age),
        )
    if len(snapshot.datasources) > 10:
        datasource_table.add_row(
            Text(f"… {len(snapshot.datasources) - 10} more", style="dim"),
            "",
            "",
            "",
            "",
            "",
        )

    recent_table = Table(
        title="Recent requests",
        box=box.SIMPLE,
        expand=True,
        padding=(0, 1),
    )
    compact = width < 100
    if not compact:
        recent_table.add_column("Time", no_wrap=True)
        recent_table.add_column("Method", no_wrap=True)
    recent_table.add_column("Route", ratio=2, overflow="ellipsis")
    recent_table.add_column("Datasources", ratio=3, overflow="ellipsis")
    recent_table.add_column("Status", justify="right")
    recent_table.add_column("Total", justify="right")
    if not compact:
        recent_table.add_column("Upstream", justify="right")
    recent_table.add_column("Body out" if compact else "Bodies", justify="right")
    for sample in snapshot.recent:
        datasource_text = ", ".join(
            f"{uid}×{targets}" if targets > 1 else uid
            for uid, targets in sample.datasources.items()
        )
        status = (
            "disconnect"
            if sample.disconnected
            else str(sample.status)
            if sample.status is not None
            else "error"
        )
        status_style = (
            "red"
            if sample.disconnected or sample.status is None or sample.status >= 500
            else "yellow"
            if sample.status >= 400
            else "green"
        )
        cells: list[str | Text] = [] if compact else [sample.when, sample.method]
        cells.extend(
            [
                sample.route,
                Text(datasource_text or "—"),
                Text(status, style=status_style),
                format_latency(sample.duration),
            ]
        )
        if not compact:
            cells.append(format_latency(sample.upstream_duration))
        cells.append(
            format_bytes(sample.response_bytes)
            if compact
            else f"{format_bytes(sample.request_bytes)} → {format_bytes(sample.response_bytes)}"
        )
        recent_table.add_row(*cells)
    if not snapshot.recent:
        recent_table.add_row(
            Text("Waiting for requests…", style="dim"),
            *([""] * (4 if compact else 7)),
        )
    return Group(overview, datasource_table, recent_table)


def is_client_disconnect(e: BaseException) -> bool:
    if isinstance(e, (BrokenPipeError, ConnectionResetError)):
        return True
    return isinstance(e, OSError) and e.errno in CLIENT_DISCONNECT_ERRNOS


def request_route(path: str) -> str:
    path = urlsplit(path).path
    if path in ("/-/healthy", "/-/ready"):
        return "health"
    if path == "/api/ds/query":
        return "ds/query"
    if path.startswith(("/prometheus/", "/api/v1/")):
        return "prometheus"
    if path.startswith("/elasticsearch/"):
        return "elasticsearch"
    if path.startswith("/rqlite/"):
        return "rqlite"
    return "other"


def client(
    url: str,
    token: str | None,
    username: str | None,
    password: str | None,
    host: str | None,
    sni_hostname: str | None,
    verify: bool,
    timeout: float,
) -> httpx.Client:
    global REQUEST_EXTENSIONS
    if token and (username is not None or password is not None):
        raise click.UsageError("--token cannot be combined with basic authentication")
    if (username is None) != (password is None):
        raise click.UsageError(
            "basic authentication requires both --username and --password"
        )
    auth = (
        httpx.BasicAuth(username, password)
        if username is not None and password is not None
        else None
    )
    REQUEST_EXTENSIONS = {"sni_hostname": sni_hostname} if sni_hostname else {}
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host:
        headers["Host"] = host
    return httpx.Client(
        base_url=url.rstrip("/"),
        headers=headers,
        auth=auth,
        verify=verify,
        timeout=timeout,
    )


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


def alert_rule_path(namespace: str, name: str | None = None) -> str:
    path = ALERT_RULES_APP_PATH.format(namespace=quote(namespace, safe=""))
    return f"{path}/{quote(name, safe='')}" if name else path


def load_document(path: str) -> Any:
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise click.UsageError(f"invalid JSON/YAML in {path}: {e}") from e


def print_response(r: httpx.Response) -> int:
    if r.status_code >= 400:
        print(f"HTTP {r.status_code}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        return 1
    if not r.content:
        return 0
    try:
        body = r.json()
    except json.JSONDecodeError:
        print(r.text)
    else:
        print(json.dumps(body, indent=2, ensure_ascii=False))
    return 0


def fetch_alert_rule(
    c: httpx.Client, namespace: str, name: str
) -> tuple[dict[str, Any] | None, int]:
    r = c.get(
        alert_rule_path(namespace, name),
        extensions=REQUEST_EXTENSIONS,
    )
    if r.status_code >= 400:
        return None, print_response(r)
    body = r.json()
    if not isinstance(body, dict):
        raise click.ClickException("Grafana returned a non-object alert rule")
    return cast(dict[str, Any], body), 0


def fetch_alert_rules(c: httpx.Client, namespace: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    continue_token: str | None = None
    while True:
        params: dict[str, str | int] = {"limit": 1000}
        if continue_token:
            params["continue"] = continue_token
        response = c.get(
            alert_rule_path(namespace),
            params=params,
            extensions=REQUEST_EXTENSIONS,
        )
        if response.status_code >= 400:
            raise click.ClickException(
                f"Grafana returned HTTP {response.status_code}: {response.text}"
            )
        body = response.json()
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise click.ClickException("Grafana returned an invalid alert-rule list")
        rules.extend(cast(list[dict[str, Any]], items))
        metadata = body.get("metadata", {})
        continue_token = (
            metadata.get("continue") if isinstance(metadata, dict) else None
        )
        if not isinstance(continue_token, str) or not continue_token:
            return rules


def elasticsearch_alert_query(
    rule: dict[str, Any], datasource_uids: frozenset[str]
) -> ElasticsearchAlertQuery | None:
    spec = rule.get("spec")
    expressions = spec.get("expressions") if isinstance(spec, dict) else None
    if not isinstance(expressions, dict):
        return None

    matches: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []
    for ref_id, expression_value in expressions.items():
        if not isinstance(ref_id, str) or not isinstance(expression_value, dict):
            continue
        expression = cast(dict[str, Any], expression_value)
        model_value = expression.get("model")
        if not isinstance(model_value, dict):
            continue
        model = cast(dict[str, Any], model_value)
        datasource = model.get("datasource")
        if (
            not isinstance(datasource, dict)
            or datasource.get("type") != "elasticsearch"
        ):
            continue
        datasource_uid = expression.get("datasourceUID") or datasource.get("uid")
        if not isinstance(datasource_uid, str) or not datasource_uid:
            raise ValueError(
                f"Elasticsearch expression {ref_id!r} has no datasource UID"
            )
        if datasource_uids and datasource_uid not in datasource_uids:
            continue
        matches.append((ref_id, expression, model, datasource_uid))

    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("has multiple Elasticsearch queries")

    ref_id, expression, model, datasource_uid = matches[0]
    query_type = model.get("queryType") or expression.get("queryType") or "lucene"
    if query_type != "lucene":
        raise ValueError(
            f"Elasticsearch expression {ref_id!r} uses unsupported query type {query_type!r}"
        )
    if model.get("hide") is True:
        raise ValueError(f"Elasticsearch expression {ref_id!r} is hidden")
    if not isinstance(model.get("query", ""), str):
        raise ValueError(f"Elasticsearch expression {ref_id!r} has no string query")

    bucket_aggs = model.get("bucketAggs", [])
    term_fields: list[str] = []
    if isinstance(bucket_aggs, list):
        for aggregation in bucket_aggs:
            if not isinstance(aggregation, dict) or aggregation.get("type") != "terms":
                continue
            field_name = aggregation.get("field")
            if (
                isinstance(field_name, str)
                and field_name
                and field_name not in term_fields
            ):
                term_fields.append(field_name)
    return ElasticsearchAlertQuery(
        ref_id=ref_id,
        datasource_uid=datasource_uid,
        model=model,
        term_fields=tuple(term_fields),
    )


def go_template_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def lucene_escape_term(value: str) -> str:
    value = re.sub(r"(&&|\|\||[+\-!(){}\[\]^\"~*?:\\/])", r"\\\1", value)
    return re.sub(r"\s", lambda match: "\\" + match.group(), value)


def build_elasticsearch_explore_link(query: ElasticsearchAlertQuery) -> str:
    model = query.model
    runtime_query = str(model.get("query", ""))
    parts = [
        ELASTICSEARCH_EXPLORE_LINK_START,
        f"{{{{ $query := {go_template_string(runtime_query)} }}}}",
    ]
    for field_name in query.term_fields:
        escaped_field = lucene_escape_term(field_name).replace("%", "%%")
        filter_format = go_template_string(f"%s AND {escaped_field}:%q")
        label = go_template_string(field_name)
        parts.append(
            f"{{{{ with $value := index $labels {label} }}}}"
            f"{{{{ $query = printf {filter_format} $query $value }}}}"
            "{{ end }}"
        )

    explore_query: dict[str, Any] = {
        "refId": query.ref_id,
        "datasource": {"type": "elasticsearch", "uid": query.datasource_uid},
        "query": ELASTICSEARCH_EXPLORE_QUERY_SENTINEL,
        "queryType": "lucene",
        "metrics": [{"id": "1", "type": "logs", "settings": {"limit": "500"}}],
        "bucketAggs": [],
    }
    for field_name in ("editorType", "timeField"):
        value = model.get(field_name)
        if isinstance(value, str) and value:
            explore_query[field_name] = value
    panes = {
        "log": {
            "datasource": query.datasource_uid,
            "queries": [explore_query],
            "range": {"from": "now-30m", "to": "now"},
        }
    }
    panes_format = json.dumps(panes, ensure_ascii=False, separators=(",", ":"))
    panes_format = panes_format.replace("%", "%%").replace(
        go_template_string(ELASTICSEARCH_EXPLORE_QUERY_SENTINEL), "%q"
    )
    parts.extend(
        (
            f"{{{{ $panes := printf {go_template_string(panes_format)} $query }}}}",
            f"{ELASTICSEARCH_EXPLORE_LINK_LABEL} "
            "{{ externalURL }}explore?schemaVersion=1&panes="
            "{{ $panes | urlquery }}&orgId=1",
            ELASTICSEARCH_EXPLORE_LINK_END,
        )
    )
    return "".join(parts)


def reconcile_elasticsearch_explore_description(
    description: str, explore_link: str
) -> str:
    start_count = description.count(ELASTICSEARCH_EXPLORE_LINK_START)
    end_count = description.count(ELASTICSEARCH_EXPLORE_LINK_END)
    if start_count != end_count or start_count > 1:
        raise ValueError("description has malformed managed Explore-link markers")
    if start_count:
        return ELASTICSEARCH_EXPLORE_LINK_RE.sub(explore_link, description)

    description = ELASTICSEARCH_LEGACY_EXPLORE_LINK_RE.sub("", description)
    description = description.rstrip("\n")
    return f"{description}\n{explore_link}" if description else explore_link


def prepare_alert_rule(
    source: Any,
    namespace: str,
    name: str | None = None,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise click.UsageError("alert rule must be a JSON/YAML object")
    rule = copy.deepcopy(cast(dict[str, Any], source))
    if rule.get("apiVersion") != ALERT_RULE_API_VERSION:
        raise click.UsageError(
            f"alert rule apiVersion must be {ALERT_RULE_API_VERSION}"
        )
    if rule.get("kind") != ALERT_RULE_KIND:
        raise click.UsageError(f"alert rule kind must be {ALERT_RULE_KIND}")
    if not isinstance(rule.get("spec"), dict):
        raise click.UsageError("alert rule spec must be an object")

    metadata = rule.get("metadata")
    if not isinstance(metadata, dict):
        raise click.UsageError("alert rule metadata must be an object")
    metadata = cast(dict[str, Any], metadata)
    source_name = metadata.get("name")
    if name and source_name not in (None, name):
        raise click.UsageError(
            f"alert rule metadata.name {source_name!r} does not match {name!r}"
        )
    metadata["name"] = name or source_name
    if not isinstance(metadata["name"], str) or not metadata["name"]:
        raise click.UsageError("alert rule metadata.name is required")
    source_namespace = metadata.get("namespace")
    if source_namespace not in (None, namespace):
        raise click.UsageError(
            f"alert rule metadata.namespace {source_namespace!r} does not match {namespace!r}"
        )
    metadata["namespace"] = namespace

    for metadata_field in ALERT_RULE_SERVER_METADATA_FIELDS:
        metadata.pop(metadata_field, None)
    rule.pop("status", None)
    annotations = metadata.setdefault("annotations", {})
    if not isinstance(annotations, dict):
        raise click.UsageError("alert rule metadata.annotations must be an object")
    for annotation in ALERT_RULE_SERVER_ANNOTATIONS:
        annotations.pop(annotation, None)

    if current is None:
        metadata.pop("resourceVersion", None)
        return rule

    current_metadata = current.get("metadata", {})
    if not isinstance(current_metadata, dict):
        raise click.ClickException("Grafana returned invalid alert-rule metadata")
    if "resourceVersion" not in metadata and current_metadata.get("resourceVersion"):
        metadata["resourceVersion"] = current_metadata["resourceVersion"]
    current_annotations = current_metadata.get("annotations", {})
    if not isinstance(current_annotations, dict):
        raise click.UsageError("alert rule metadata.annotations must be an object")
    for key in ALERT_RULE_MANAGER_ANNOTATIONS:
        if key in current_annotations:
            annotations.setdefault(key, current_annotations[key])
    return rule


_PROM_DURATION_RE = re.compile(
    r"^(?:(?P<y>[0-9]+)y)?(?:(?P<w>[0-9]+)w)?(?:(?P<d>[0-9]+)d)?"
    r"(?:(?P<h>[0-9]+)h)?(?:(?P<m>[0-9]+)m)?(?:(?P<s>[0-9]+)s)?$"
)
_PROM_DURATION_UNIT_SECONDS = {
    "y": 365 * 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
    "d": 24 * 60 * 60,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
}


def parse_prom_duration_seconds(value: Any, field_name: str) -> int:
    if value == "0":
        return 0
    if not isinstance(value, str) or not value:
        raise click.UsageError(f"{field_name} must be a Prometheus duration")
    match = _PROM_DURATION_RE.fullmatch(value)
    if match is None or not any(match.groupdict().values()):
        raise click.UsageError(
            f"{field_name} has invalid Prometheus duration {value!r}"
        )
    return sum(
        int(amount) * _PROM_DURATION_UNIT_SECONDS[unit]
        for unit, amount in match.groupdict().items()
        if amount is not None
    )


def app_alert_rule_to_provisioning(rule: dict[str, Any]) -> dict[str, Any]:
    metadata = cast(dict[str, Any], rule["metadata"])
    spec = cast(dict[str, Any], rule["spec"])
    annotations = metadata.get("annotations", {})
    labels = metadata.get("labels", {})
    if not isinstance(annotations, dict) or not isinstance(labels, dict):
        raise click.UsageError("alert rule metadata labels/annotations must be objects")

    folder_uid = annotations.get(ALERT_RULE_FOLDER_KEY) or labels.get(
        ALERT_RULE_FOLDER_KEY
    )
    if not isinstance(folder_uid, str) or not folder_uid:
        raise click.UsageError(
            f"alert rule metadata must set {ALERT_RULE_FOLDER_KEY!r}"
        )
    group = labels.get(ALERT_RULE_GROUP_KEY)
    if not isinstance(group, str) or not group:
        raise click.UsageError(
            f"alert rule metadata.labels must set {ALERT_RULE_GROUP_KEY!r}"
        )

    expressions = spec.get("expressions")
    if not isinstance(expressions, dict) or not expressions:
        raise click.UsageError("alert rule spec.expressions must be a non-empty object")
    condition: str | None = None
    data: list[dict[str, Any]] = []
    for ref_id, expression_value in expressions.items():
        if not isinstance(ref_id, str) or not ref_id:
            raise click.UsageError(
                "alert rule expression IDs must be non-empty strings"
            )
        if not isinstance(expression_value, dict):
            raise click.UsageError(
                f"alert rule expression {ref_id!r} must be an object"
            )
        expression = cast(dict[str, Any], expression_value)
        if expression.get("source") is True:
            if condition is not None:
                raise click.UsageError(
                    f"multiple alert rule expressions are marked source: "
                    f"{condition!r} and {ref_id!r}"
                )
            condition = ref_id
        relative_range = expression.get("relativeTimeRange", {})
        if not isinstance(relative_range, dict):
            raise click.UsageError(
                f"alert rule expression {ref_id!r} relativeTimeRange must be an object"
            )
        data.append(
            {
                "refId": ref_id,
                "queryType": expression.get("queryType", ""),
                "relativeTimeRange": {
                    "from": parse_prom_duration_seconds(
                        relative_range.get("from", "0s"),
                        f"expression {ref_id} relativeTimeRange.from",
                    ),
                    "to": parse_prom_duration_seconds(
                        relative_range.get("to", "0s"),
                        f"expression {ref_id} relativeTimeRange.to",
                    ),
                },
                "datasourceUid": expression.get("datasourceUID", "__expr__"),
                "model": expression.get("model", {}),
            }
        )
    if condition is None:
        raise click.UsageError(
            "exactly one alert rule expression must set source: true"
        )

    no_data_states = {
        "Ok": "OK",
        "NoData": "NoData",
        "Alerting": "Alerting",
        "KeepLast": "KeepLast",
    }
    exec_err_states = {
        "Ok": "OK",
        "Error": "Error",
        "Alerting": "Alerting",
        "KeepLast": "KeepLast",
    }
    no_data_state = spec.get("noDataState", "NoData")
    exec_err_state = spec.get("execErrState", "Error")
    if no_data_state not in no_data_states:
        raise click.UsageError(f"invalid alert rule noDataState {no_data_state!r}")
    if exec_err_state not in exec_err_states:
        raise click.UsageError(f"invalid alert rule execErrState {exec_err_state!r}")

    body: dict[str, Any] = {
        "uid": metadata["name"],
        "folderUID": folder_uid,
        "ruleGroup": group,
        "title": spec.get("title", ""),
        "condition": condition,
        "data": data,
        "noDataState": no_data_states[no_data_state],
        "execErrState": exec_err_states[exec_err_state],
        "for": spec.get("for", "0s"),
        "annotations": spec.get("annotations", {}),
        "labels": spec.get("labels", {}),
        "isPaused": spec.get("paused", False),
    }
    if "keepFiringFor" in spec:
        body["keep_firing_for"] = spec["keepFiringFor"]
    if "missingSeriesEvalsToResolve" in spec:
        body["missingSeriesEvalsToResolve"] = spec["missingSeriesEvalsToResolve"]

    notification_settings = spec.get("notificationSettings")
    if notification_settings is not None:
        if not isinstance(notification_settings, dict):
            raise click.UsageError(
                "alert rule spec.notificationSettings must be an object"
            )
        if notification_settings.get("type") != "SimplifiedRouting":
            raise click.UsageError(
                "create supports only SimplifiedRouting notification settings"
            )
        field_names = {
            "receiver": "receiver",
            "groupBy": "group_by",
            "groupWait": "group_wait",
            "groupInterval": "group_interval",
            "repeatInterval": "repeat_interval",
            "muteTimeIntervals": "mute_time_intervals",
            "activeTimeIntervals": "active_time_intervals",
        }
        body["notification_settings"] = {
            target: notification_settings[source]
            for source, target in field_names.items()
            if source in notification_settings
        }
    return body


def alert_rule_manager(rule: dict[str, Any]) -> str | None:
    metadata = rule.get("metadata", {})
    annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
    if not isinstance(annotations, dict):
        return None
    manager = annotations.get("grafana.app/managedBy")
    provenance = annotations.get("grafana.com/provenance")
    if manager:
        return f"managed by {manager}"
    if provenance:
        return f"provenance {provenance}"
    return None


def check_alert_rule_manager(rule: dict[str, Any], allow_managed: bool) -> None:
    manager = alert_rule_manager(rule)
    if manager and not allow_managed:
        raise click.UsageError(
            f"alert rule is {manager}; pass --allow-managed to modify it"
        )


def mutate_alert_rule(
    c: httpx.Client,
    method: str,
    path: str,
    content: bytes | None,
    content_type: str | None,
    prompt: str,
    dry_run: bool,
    yes: bool,
    strict: bool = True,
    extra_params: dict[str, str | bool] | None = None,
) -> int:
    params: dict[str, str | bool] = dict(extra_params or {})
    if strict:
        params["fieldValidation"] = "Strict"
    headers = {"Content-Type": content_type} if content_type else None

    if dry_run:
        print(
            "Dry run: local validation passed; no write request sent.", file=sys.stderr
        )
        return 0

    if not yes and not click.confirm(prompt):
        print("Cancelled.", file=sys.stderr)
        return 0
    response = c.request(
        method,
        path,
        params=params,
        content=content,
        headers=headers,
        extensions=REQUEST_EXTENSIONS,
    )
    return print_response(response)


def json_content(body: Any) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode()


def cmd_alert_rule_get(c: httpx.Client, args: Any) -> int:
    rule, result = fetch_alert_rule(c, args.namespace, args.name)
    if rule is not None:
        print(json.dumps(rule, indent=2, ensure_ascii=False))
    return result


def cmd_alert_rule_create(c: httpx.Client, args: Any) -> int:
    rule = prepare_alert_rule(load_document(args.file), args.namespace)
    check_alert_rule_manager(rule, args.allow_managed)
    name = cast(dict[str, Any], rule["metadata"])["name"]
    body = app_alert_rule_to_provisioning(rule)
    if args.dry_run:
        print(
            "Dry run: local validation passed; no write request sent.", file=sys.stderr
        )
        return 0
    if not args.yes and not click.confirm(f"Create alert rule {name}?"):
        print("Cancelled.", file=sys.stderr)
        return 0
    response = c.post(
        ALERT_RULE_PROVISIONING_PATH,
        content=json_content(body),
        headers={
            "Content-Type": "application/json",
            "X-Disable-Provenance": "true",
        },
        extensions=REQUEST_EXTENSIONS,
    )
    if response.status_code >= 400:
        return print_response(response)
    created, result = fetch_alert_rule(c, args.namespace, name)
    if created is not None:
        print(json.dumps(created, indent=2, ensure_ascii=False))
    return result


def cmd_alert_rule_reconcile_explore_links(c: httpx.Client, args: Any) -> int:
    if args.check and args.yes:
        raise click.UsageError("--check and --yes cannot be combined")

    rules = fetch_alert_rules(c, args.namespace)
    datasource_uids = frozenset(args.datasource_uid)
    changes: list[ExploreLinkChange] = []
    errors: list[str] = []
    matched = 0
    unchanged = 0
    managed = 0

    for rule in rules:
        metadata = rule.get("metadata", {})
        spec = rule.get("spec", {})
        name = metadata.get("name") if isinstance(metadata, dict) else None
        title = spec.get("title") if isinstance(spec, dict) else None
        display_name = name if isinstance(name, str) and name else "<unnamed>"
        display_title = title if isinstance(title, str) and title else display_name

        try:
            query = elasticsearch_alert_query(rule, datasource_uids)
        except ValueError as error:
            errors.append(f"{display_name}: {error}")
            continue
        if query is None:
            continue
        matched += 1

        if not isinstance(name, str) or not name:
            errors.append(f"{display_name}: has no metadata.name")
            continue
        resource_version = (
            metadata.get("resourceVersion") if isinstance(metadata, dict) else None
        )
        if not isinstance(resource_version, str) or not resource_version:
            errors.append(f"{display_name}: has no metadata.resourceVersion")
            continue
        annotations = spec.get("annotations", {}) if isinstance(spec, dict) else {}
        if not isinstance(annotations, dict):
            errors.append(f"{display_name}: spec.annotations is not an object")
            continue
        description = annotations.get("description", "")
        if not isinstance(description, str):
            errors.append(
                f"{display_name}: spec.annotations.description is not a string"
            )
            continue
        try:
            reconciled = reconcile_elasticsearch_explore_description(
                description,
                build_elasticsearch_explore_link(query),
            )
        except ValueError as error:
            errors.append(f"{display_name}: {error}")
            continue
        if reconciled == description:
            unchanged += 1
            continue

        manager = alert_rule_manager(rule)
        if manager and not args.allow_managed:
            managed += 1
            print(f"SKIP {name}: {display_title} ({manager})")
            continue
        changes.append(
            ExploreLinkChange(
                name=name,
                title=display_title,
                rule=rule,
                query=query,
                description=reconciled,
            )
        )

    action = "STALE" if args.check else "UPDATE" if args.yes else "WOULD UPDATE"
    for change in changes:
        term_fields = ", ".join(change.query.term_fields) or "none"
        print(
            f"{action} {change.name}: {change.title} "
            f"[datasource={change.query.datasource_uid}, "
            f"query={change.query.ref_id}, terms={term_fields}]"
        )
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)

    print(
        f"Elasticsearch alert rules: {matched} matched, {len(changes)} changed, "
        f"{unchanged} current, {managed} managed skipped, {len(errors)} errors."
    )
    if errors:
        print("No changes applied because validation failed.", file=sys.stderr)
        return 1
    if args.check:
        return 1 if changes else 0
    if not args.yes:
        if changes:
            print("Preview only; pass --yes to apply these changes.")
        return 0

    failed = 0
    for change in changes:
        content = prepare_alert_rule_patch(
            {"spec": {"annotations": {"description": change.description}}},
            "merge",
            args.namespace,
            change.name,
            change.rule,
        )
        response = c.patch(
            alert_rule_path(args.namespace, change.name),
            params={"fieldValidation": "Strict"},
            content=content,
            headers={
                "Content-Type": ALERT_RULE_PATCH_CONTENT_TYPES["merge"],
            },
            extensions=REQUEST_EXTENSIONS,
        )
        if response.status_code >= 400:
            failed += 1
            print(
                f"ERROR {change.name}: HTTP {response.status_code}: {response.text}",
                file=sys.stderr,
            )
        else:
            print(f"UPDATED {change.name}: {change.title}")
    return 1 if failed else 0


def cmd_alert_rule_replace(c: httpx.Client, args: Any) -> int:
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    rule = prepare_alert_rule(
        load_document(args.file),
        args.namespace,
        args.name,
        current,
    )
    check_alert_rule_manager(rule, args.allow_managed)
    return mutate_alert_rule(
        c,
        "PUT",
        alert_rule_path(args.namespace, args.name),
        json_content(rule),
        "application/json",
        f"Replace alert rule {args.name}?",
        args.dry_run,
        args.yes,
    )


def prepare_alert_rule_patch(
    source: Any,
    patch_type: str,
    namespace: str,
    name: str,
    current: dict[str, Any],
) -> bytes:
    metadata = current.get("metadata", {})
    resource_version = (
        metadata.get("resourceVersion") if isinstance(metadata, dict) else None
    )
    if patch_type == "json":
        if not isinstance(source, list):
            raise click.UsageError("JSON patch must be an array")
        patch = copy.deepcopy(source)
        if resource_version:
            patch.insert(
                0,
                {
                    "op": "test",
                    "path": "/metadata/resourceVersion",
                    "value": resource_version,
                },
            )
        return json_content(patch)
    if patch_type == "merge":
        if not isinstance(source, dict):
            raise click.UsageError("merge patch must be an object")
        patch = copy.deepcopy(source)
        patch_metadata = patch.setdefault("metadata", {})
        if not isinstance(patch_metadata, dict):
            raise click.UsageError("merge patch metadata must be an object")
        if resource_version:
            patch_metadata.setdefault("resourceVersion", resource_version)
        return json_content(patch)
    rule = prepare_alert_rule(source, namespace, name)
    return yaml.safe_dump(rule, sort_keys=False).encode()


def cmd_alert_rule_patch(c: httpx.Client, args: Any) -> int:
    if args.force and args.patch_type != "apply":
        raise click.UsageError("--force is supported only with --type apply")
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    content = prepare_alert_rule_patch(
        load_document(args.file),
        args.patch_type,
        args.namespace,
        args.name,
        current,
    )
    params: dict[str, str | bool] = {}
    if args.patch_type == "apply":
        params["fieldManager"] = args.field_manager
        if args.force:
            params["force"] = True
    return mutate_alert_rule(
        c,
        "PATCH",
        alert_rule_path(args.namespace, args.name),
        content,
        ALERT_RULE_PATCH_CONTENT_TYPES[args.patch_type],
        f"Patch alert rule {args.name}?",
        args.dry_run,
        args.yes,
        extra_params=params,
    )


def cmd_alert_rule_edit(c: httpx.Client, args: Any) -> int:
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    rule = prepare_alert_rule(current, args.namespace, args.name, current)
    original = json.dumps(rule, indent=2, ensure_ascii=False) + "\n"
    edited = click.edit(original, extension=".json")
    if edited is None:
        print("No changes.", file=sys.stderr)
        return 0
    try:
        edited_rule = prepare_alert_rule(
            json.loads(edited),
            args.namespace,
            args.name,
            current,
        )
    except json.JSONDecodeError as e:
        raise click.UsageError(f"invalid edited JSON: {e}") from e
    check_alert_rule_manager(edited_rule, args.allow_managed)
    if edited_rule == rule:
        print("No changes.", file=sys.stderr)
        return 0

    updated = json.dumps(edited_rule, indent=2, ensure_ascii=False) + "\n"
    sys.stderr.writelines(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"{args.name}.before.json",
            tofile=f"{args.name}.after.json",
        )
    )
    return mutate_alert_rule(
        c,
        "PUT",
        alert_rule_path(args.namespace, args.name),
        json_content(edited_rule),
        "application/json",
        f"Update alert rule {args.name}?",
        args.dry_run,
        args.yes,
    )


def cmd_alert_rule_delete(c: httpx.Client, args: Any) -> int:
    current, result = fetch_alert_rule(c, args.namespace, args.name)
    if current is None:
        return result
    check_alert_rule_manager(current, args.allow_managed)
    return mutate_alert_rule(
        c,
        "DELETE",
        alert_rule_path(args.namespace, args.name),
        None,
        None,
        f"Delete alert rule {args.name}?",
        args.dry_run,
        args.yes,
        strict=False,
    )


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


class PrometheusApiProxyHandler(BaseHTTPRequestHandler):
    grafana_client: httpx.Client
    uid: str
    quiet: bool = False
    stats: ProxyStats
    datasource_types: dict[str, str]
    _sample: RequestSample

    def do_GET(self) -> None:
        self._handle_safely()

    def do_HEAD(self) -> None:
        self._handle_safely()

    def do_POST(self) -> None:
        self._handle_safely()

    def do_OPTIONS(self) -> None:
        self._handle_safely(options_only=True)

    def log_message(self, format: str, *args: Any) -> None:
        if not self.quiet:
            super().log_message(format, *args)

    def send_response(self, code: int, message: str | None = None) -> None:
        if hasattr(self, "_sample"):
            self._sample.status = code
        super().send_response(code, message)

    def _handle_safely(self, options_only: bool = False) -> None:
        try:
            request_bytes = max(0, int(self.headers.get("Content-Length", "0")))
        except ValueError:
            request_bytes = 0
        self._sample = RequestSample(
            method=self.command,
            route=request_route(self.path),
            request_bytes=request_bytes,
        )
        self.stats.begin(self._sample)
        try:
            if options_only:
                self.send_response(204)
                self._write_cors_headers()
                self.end_headers()
            else:
                self._handle()
        except OSError as e:
            if not is_client_disconnect(e):
                raise
            self._sample.disconnected = True
            if not self.quiet:
                self.log_error("client disconnected before response completed: %s", e)
        finally:
            self._sample.duration = time.monotonic() - self._sample.started
            self.stats.finish(self._sample)

    def _use_datasource(
        self,
        uid: str,
        datasource_type: str = "",
        targets: int = 1,
    ) -> None:
        self._sample.datasources[uid] += targets
        self._sample.datasource_types[uid] = (
            datasource_type or self.datasource_types.get(uid, "unknown")
        )

    def _request_upstream(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        started = time.monotonic()
        try:
            return self.grafana_client.request(method, path, **kwargs)
        finally:
            elapsed = time.monotonic() - started
            self._sample.upstream_duration = (
                self._sample.upstream_duration or 0
            ) + elapsed

    def _handle(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in ("/-/healthy", "/-/ready"):
            self._write_text(200, "Prometheus API facade is ready.\n")
            return
        if not parsed.path.startswith("/api/v1/"):
            self._write_json(
                404,
                {
                    "status": "error",
                    "errorType": "not_found",
                    "error": f"unsupported path: {parsed.path}",
                },
            )
            return

        try:
            upstream = self._forward_to_grafana(parsed)
        except httpx.HTTPError as e:
            self._write_json(
                502,
                {
                    "status": "error",
                    "errorType": "bad_gateway",
                    "error": str(e),
                },
            )
            return

        self._write_upstream_response(upstream)

    def _forward_to_grafana(self, parsed) -> httpx.Response:
        content = b""
        if self.command == "POST":
            length = int(self.headers.get("Content-Length", "0"))
            if length > 0:
                content = self.rfile.read(length)

        proxy_path = (
            f"/api/datasources/proxy/uid/{quote(self.uid, safe='')}{parsed.path}"
        )
        if parsed.query:
            proxy_path = f"{proxy_path}?{parsed.query}"

        headers = {}
        content_type = self.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type
        accept = self.headers.get("Accept")
        if accept:
            headers["Accept"] = accept

        self._use_datasource(self.uid, "prometheus")
        return self._request_upstream(
            self.command,
            proxy_path,
            content=content if self.command == "POST" else None,
            headers=headers,
            extensions=REQUEST_EXTENSIONS,
        )

    def _write_upstream_response(self, upstream: httpx.Response) -> None:
        self._sample.response_bytes = (
            0 if self.command == "HEAD" else len(upstream.content)
        )
        self.send_response(upstream.status_code)
        self._write_cors_headers()
        for name, value in upstream.headers.items():
            lname = name.lower()
            if lname in {
                "access-control-allow-headers",
                "access-control-allow-methods",
                "access-control-allow-origin",
                "connection",
                "content-encoding",
                "content-length",
                "date",
                "server",
                "transfer-encoding",
            }:
                continue
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(upstream.content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(upstream.content)

    def _write_json(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self._sample.response_bytes = 0 if self.command == "HEAD" else len(raw)
        self.send_response(status)
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _write_text(self, status: int, body: str) -> None:
        raw = body.encode("utf-8")
        self._sample.response_bytes = 0 if self.command == "HEAD" else len(raw)
        self.send_response(status)
        self._write_cors_headers()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _write_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")


class QueryApiValidationError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class GrafanaQueryApiProxyHandler(PrometheusApiProxyHandler):
    allowed_uids: frozenset[str]
    cors_origins: frozenset[str]
    prometheus_uids: frozenset[str] = frozenset()
    elasticsearch_uids: frozenset[str] = frozenset()
    rqlite_uid: str | None = None
    max_body_bytes: int = DEFAULT_QUERY_API_MAX_BODY_BYTES

    def _write_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and ("*" in self.cors_origins or origin in self.cors_origins):
            self.send_header(
                "Access-Control-Allow-Origin",
                "*" if "*" in self.cors_origins else origin,
            )
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Accept, X-Grafana-Device-Id, X-Request-Id",
        )

    def _handle(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in ("/-/healthy", "/-/ready"):
            self._write_json(
                200,
                {
                    "status": "ok",
                    "allowedDatasourceUids": sorted(self.allowed_uids),
                    "prometheusDatasourceUids": sorted(self.prometheus_uids),
                    "elasticsearchDatasourceUids": sorted(self.elasticsearch_uids),
                    "rqliteDatasourceUid": self.rqlite_uid,
                },
            )
            return
        if parsed.path.startswith("/rqlite/"):
            self._handle_rqlite(parsed)
            return
        if parsed.path.startswith("/prometheus/"):
            self._handle_prometheus(parsed)
            return
        if parsed.path.startswith("/elasticsearch/"):
            self._handle_elasticsearch(parsed)
            return
        if parsed.path != "/api/ds/query":
            self._write_json(404, {"message": f"unsupported path: {parsed.path}"})
            return
        if self.command != "POST":
            self._write_json(405, {"message": "POST required"})
            return

        try:
            content = self._read_and_validate_query_body()
        except QueryApiValidationError as e:
            self._write_json(e.status, {"message": str(e)})
            return

        upstream_path = parsed.path
        if parsed.query:
            upstream_path = f"{upstream_path}?{parsed.query}"
        try:
            upstream = self._request_upstream(
                "POST",
                upstream_path,
                content=content,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                extensions=REQUEST_EXTENSIONS,
            )
        except httpx.HTTPError as e:
            self._write_json(502, {"message": f"upstream Grafana query failed: {e}"})
            return
        self._write_upstream_response(upstream)

    def _handle_elasticsearch(self, parsed) -> None:
        remainder = parsed.path.removeprefix("/elasticsearch/")
        encoded_uid, separator, path = remainder.partition("/")
        uid = unquote(encoded_uid).strip()
        if not uid:
            self._write_json(
                404, {"message": "Elasticsearch datasource UID is required"}
            )
            return
        if uid not in self.elasticsearch_uids:
            self._write_json(
                403,
                {"message": f"Elasticsearch datasource UID not allowed: {uid}"},
            )
            return

        upstream_path = f"/{path}" if separator else "/"
        if self.command not in ("GET", "HEAD", "POST"):
            self._write_json(405, {"message": "GET, HEAD, or POST required"})
            return
        if self.command == "POST" and not self._is_elasticsearch_read_post(
            upstream_path
        ):
            self._write_json(
                403,
                {"message": f"unsupported Elasticsearch read path: {upstream_path}"},
            )
            return

        try:
            content = self._read_bounded_body() if self.command == "POST" else None
        except QueryApiValidationError as e:
            self._write_json(e.status, {"message": str(e)})
            return

        proxy_path = f"/api/datasources/proxy/uid/{quote(uid, safe='')}{upstream_path}"
        if parsed.query:
            proxy_path = f"{proxy_path}?{parsed.query}"
        headers = {}
        for name in ("Content-Type", "Accept"):
            value = self.headers.get(name)
            if value:
                headers[name] = value
        self._use_datasource(uid, "elasticsearch")
        try:
            upstream = self._request_upstream(
                self.command,
                proxy_path,
                content=content,
                headers=headers,
                extensions=REQUEST_EXTENSIONS,
            )
        except httpx.HTTPError as e:
            self._write_json(
                502, {"message": f"upstream Elasticsearch proxy failed: {e}"}
            )
            return
        self._write_upstream_response(upstream)

    @staticmethod
    def _is_elasticsearch_read_post(path: str) -> bool:
        normalized = path.rstrip("/")
        return any(
            normalized.endswith(suffix) for suffix in ELASTICSEARCH_POST_READ_SUFFIXES
        )

    def _handle_prometheus(self, parsed) -> None:
        parts = parsed.path.split("/", 3)
        if len(parts) != 4:
            self._write_json(
                404, {"message": "Prometheus datasource UID and API path are required"}
            )
            return
        uid = unquote(parts[2]).strip()
        upstream_path = "/" + parts[3]
        if uid not in self.prometheus_uids:
            self._write_json(
                403, {"message": f"Prometheus datasource UID not allowed: {uid}"}
            )
            return
        if not upstream_path.startswith("/api/v1/") or upstream_path.startswith(
            "/api/v1/admin/"
        ):
            self._write_json(
                404, {"message": f"unsupported Prometheus path: {upstream_path}"}
            )
            return
        if self.command not in ("GET", "POST"):
            self._write_json(405, {"message": "GET or POST required"})
            return

        try:
            content = self._read_bounded_body() if self.command == "POST" else None
        except QueryApiValidationError as e:
            self._write_json(e.status, {"message": str(e)})
            return
        proxy_path = f"/api/datasources/proxy/uid/{quote(uid, safe='')}{upstream_path}"
        if parsed.query:
            proxy_path = f"{proxy_path}?{parsed.query}"
        headers = {}
        for name in ("Content-Type", "Accept"):
            value = self.headers.get(name)
            if value:
                headers[name] = value
        self._use_datasource(uid, "prometheus")
        try:
            upstream = self._request_upstream(
                self.command,
                proxy_path,
                content=content,
                headers=headers,
                extensions=REQUEST_EXTENSIONS,
            )
        except httpx.HTTPError as e:
            self._write_json(502, {"message": f"upstream Prometheus proxy failed: {e}"})
            return
        self._write_upstream_response(upstream)

    def _handle_rqlite(self, parsed) -> None:
        if self.rqlite_uid is None:
            self._write_json(404, {"message": "rqlite facade is not configured"})
            return

        upstream_path = parsed.path.removeprefix("/rqlite")
        if upstream_path == "/readyz":
            if self.command != "GET":
                self._write_json(405, {"message": "GET required"})
                return
            content = None
        elif upstream_path == "/db/query":
            if self.command != "POST":
                self._write_json(405, {"message": "POST required"})
                return
            try:
                content = self._read_and_validate_rqlite_body()
            except QueryApiValidationError as e:
                self._write_json(e.status, {"message": str(e)})
                return
        else:
            self._write_json(
                404, {"message": f"unsupported rqlite path: {upstream_path}"}
            )
            return

        proxy_path = (
            f"/api/datasources/proxy/uid/{quote(self.rqlite_uid, safe='')}"
            f"{upstream_path}"
        )
        if parsed.query:
            proxy_path = f"{proxy_path}?{parsed.query}"
        self._use_datasource(self.rqlite_uid, "rqlite")
        try:
            upstream = self._request_upstream(
                self.command,
                proxy_path,
                content=content,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                extensions=REQUEST_EXTENSIONS,
            )
        except httpx.HTTPError as e:
            self._write_json(502, {"message": f"upstream rqlite proxy failed: {e}"})
            return
        self._write_upstream_response(upstream)

    def _read_and_validate_rqlite_body(self) -> bytes:
        content = self._read_bounded_body()
        try:
            statements = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise QueryApiValidationError(400, f"invalid JSON body: {e}") from e
        if not isinstance(statements, list) or not statements:
            raise QueryApiValidationError(400, "body must be a non-empty SQL array")
        for index, statement in enumerate(statements):
            sql = statement
            if isinstance(statement, list) and statement:
                sql = statement[0]
            if not isinstance(sql, str) or not sql.strip():
                raise QueryApiValidationError(
                    400,
                    f"body[{index}] must be a SQL string or parameterized SQL array",
                )
            if not re.match(
                r"^\s*(?:SELECT|WITH|PRAGMA|EXPLAIN)\b",
                sql,
                flags=re.IGNORECASE,
            ):
                raise QueryApiValidationError(
                    403,
                    f"body[{index}] is not a read-only query",
                )
        return content

    def _read_bounded_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as e:
            raise QueryApiValidationError(400, "invalid Content-Length") from e
        if length <= 0:
            raise QueryApiValidationError(400, "request body is required")
        if length > self.max_body_bytes:
            raise QueryApiValidationError(
                413,
                f"request body exceeds {self.max_body_bytes} bytes",
            )

        return self.rfile.read(length)

    def _read_and_validate_query_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as e:
            raise QueryApiValidationError(400, "invalid Content-Length") from e
        if length <= 0:
            raise QueryApiValidationError(400, "request body is required")
        if length > self.max_body_bytes:
            raise QueryApiValidationError(
                413,
                f"request body exceeds {self.max_body_bytes} bytes",
            )

        content = self.rfile.read(length)
        try:
            body = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise QueryApiValidationError(400, f"invalid JSON body: {e}") from e
        if not isinstance(body, dict):
            raise QueryApiValidationError(400, "body must be a JSON object")
        queries = body.get("queries")
        if not isinstance(queries, list) or not queries:
            raise QueryApiValidationError(400, "body.queries must be a non-empty array")

        requested_uids: Counter[str] = Counter()
        requested_types: dict[str, str] = {}
        for index, query in enumerate(queries):
            if not isinstance(query, dict):
                raise QueryApiValidationError(
                    400, f"queries[{index}] must be an object"
                )
            query = cast(dict[str, Any], query)
            datasource = query.get("datasource")
            if not isinstance(datasource, dict):
                raise QueryApiValidationError(
                    400,
                    f"queries[{index}].datasource must be an object",
                )
            uid = datasource.get("uid")
            if not isinstance(uid, str) or not uid.strip():
                raise QueryApiValidationError(
                    400,
                    f"queries[{index}].datasource.uid must be a non-empty string",
                )
            uid = uid.strip()
            requested_uids[uid] += 1
            datasource_type = datasource.get("type")
            if isinstance(datasource_type, str) and datasource_type:
                requested_types[uid] = datasource_type

        denied = sorted(set(requested_uids) - self.allowed_uids)
        if denied:
            raise QueryApiValidationError(
                403,
                f"datasource UID not allowed: {', '.join(denied)}",
            )
        for uid, targets in requested_uids.items():
            self._use_datasource(uid, requested_types.get(uid, ""), targets)
        return content


def run_proxy_server(
    server: ThreadingHTTPServer,
    stats: ProxyStats,
    title: str,
    endpoint: str,
    plain_messages: tuple[str, ...],
    exposed: bool,
    use_ui: bool,
) -> None:
    if use_ui:
        with Live(
            console=console,
            get_renderable=lambda: render_dashboard(
                stats, title, endpoint, exposed, console.size.width
            ),
            refresh_per_second=2,
            screen=True,
            redirect_stdout=False,
            redirect_stderr=False,
        ) as live:
            live.refresh()
            with contextlib.suppress(KeyboardInterrupt):
                server.serve_forever()
        return

    for message in plain_messages:
        print(message, file=sys.stderr)
    if exposed:
        print(
            "Warning: API is reachable beyond loopback; restrict it with a host firewall or private network.",
            file=sys.stderr,
        )
    print("Ctrl-C stops the server.", file=sys.stderr)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


def cmd_prom_api(c: httpx.Client, args: Any) -> int:
    if not args.no_type_check:
        ds_type = ds_type_for(c, args.uid)
        if ds_type != "prometheus":
            raise click.UsageError(
                f"prom-api: datasource {args.uid!r} has type {ds_type!r}, not 'prometheus'"
            )

    use_ui = console.is_interactive and not args.no_ui
    source_types = {args.uid: "prometheus"}
    proxy_stats = ProxyStats(source_types)

    class Handler(PrometheusApiProxyHandler):
        grafana_client = c
        uid = args.uid
        quiet = args.quiet or use_ui
        datasource_types = source_types
        stats = proxy_stats

    addr = (args.listen, args.port)
    with ThreadingHTTPServer(addr, Handler) as server:
        host = args.listen
        if host == "0.0.0.0":
            host = "127.0.0.1"
        endpoint = f"http://{host}:{args.port}"
        run_proxy_server(
            server,
            proxy_stats,
            "Grafana-backed Prometheus API",
            endpoint,
            (
                f"Serving Grafana-backed Prometheus API for {args.uid} at {endpoint}",
                "Forwarding /api/v1/... via Grafana datasource proxy.",
            ),
            args.listen not in ("127.0.0.1", "::1", "localhost"),
            use_ui,
        )
    return 0


def cmd_query_api(c: httpx.Client, args: Any) -> int:
    allowed_uids = {uid.strip() for uid in args.uid if uid.strip()}
    configured_prometheus_uids = frozenset(
        uid.strip() for uid in args.prometheus_uid if uid.strip()
    )
    allowed_uids.update(configured_prometheus_uids)
    configured_elasticsearch_uids = frozenset(
        uid.strip() for uid in args.elasticsearch_uid if uid.strip()
    )
    allowed_uids.update(configured_elasticsearch_uids)
    configured_rqlite_uid = args.rqlite_uid.strip() if args.rqlite_uid else None
    if configured_rqlite_uid:
        allowed_uids.add(configured_rqlite_uid)
    allowed_uid_set = frozenset(allowed_uids)
    if not allowed_uid_set:
        raise click.UsageError("query-api: at least one non-empty --uid is required")

    datasource_types: dict[str, str] = {}
    if not args.no_uid_check:
        for uid in sorted(allowed_uid_set):
            try:
                datasource_types[uid] = ds_type_for(c, uid)
            except httpx.HTTPStatusError as e:
                raise click.UsageError(
                    f"query-api: cannot resolve datasource {uid!r}: HTTP {e.response.status_code}"
                ) from e
        wrong_prometheus_types = sorted(
            uid
            for uid in configured_prometheus_uids
            if datasource_types.get(uid) != "prometheus"
        )
        if wrong_prometheus_types:
            raise click.UsageError(
                "query-api: --prometheus-uid must reference Prometheus datasources: "
                + ", ".join(wrong_prometheus_types)
            )
        wrong_elasticsearch_types = sorted(
            uid
            for uid in configured_elasticsearch_uids
            if datasource_types.get(uid) != "elasticsearch"
        )
        if wrong_elasticsearch_types:
            raise click.UsageError(
                "query-api: --elasticsearch-uid must reference Elasticsearch datasources: "
                + ", ".join(wrong_elasticsearch_types)
            )

    use_ui = console.is_interactive and not args.no_ui
    source_types = {uid: datasource_types.get(uid, "") for uid in allowed_uid_set}
    for uid in configured_prometheus_uids:
        source_types[uid] = source_types[uid] or "prometheus"
    for uid in configured_elasticsearch_uids:
        source_types[uid] = source_types[uid] or "elasticsearch"
    if configured_rqlite_uid:
        source_types[configured_rqlite_uid] = (
            source_types[configured_rqlite_uid] or "rqlite"
        )
    proxy_stats = ProxyStats(source_types)

    class Handler(GrafanaQueryApiProxyHandler):
        grafana_client = c
        allowed_uids = allowed_uid_set
        cors_origins = frozenset(args.cors_origin)
        prometheus_uids = configured_prometheus_uids
        elasticsearch_uids = configured_elasticsearch_uids
        rqlite_uid = configured_rqlite_uid
        max_body_bytes = args.max_body_bytes
        quiet = args.quiet or use_ui
        datasource_types = source_types
        stats = proxy_stats

    addr = (args.listen, args.port)
    with ThreadingHTTPServer(addr, Handler) as server:
        display_host = "127.0.0.1" if args.listen == "0.0.0.0" else args.listen
        endpoint = f"http://{display_host}:{args.port}/api/ds/query"
        if datasource_types:
            allowed = ", ".join(
                f"{uid} ({datasource_types[uid]})" for uid in sorted(datasource_types)
            )
        else:
            allowed = ", ".join(sorted(allowed_uid_set))
        messages = [
            f"Serving Grafana query API at {endpoint}",
            f"Allowed datasource UIDs: {allowed}",
        ]
        if configured_rqlite_uid:
            messages.append(
                f"Serving read-only rqlite facade at http://{display_host}:{args.port}/rqlite",
            )
        for uid in sorted(configured_elasticsearch_uids):
            messages.append(
                "Serving read-only Elasticsearch facade for "
                f"{uid} at http://{display_host}:{args.port}/elasticsearch/{quote(uid, safe='')}"
            )
        for uid in sorted(configured_prometheus_uids):
            messages.append(
                "Serving Prometheus facade for "
                f"{uid} at http://{display_host}:{args.port}/prometheus/{quote(uid, safe='')}"
            )
        run_proxy_server(
            server,
            proxy_stats,
            "Grafana query API",
            endpoint,
            tuple(messages),
            args.listen not in ("127.0.0.1", "::1", "localhost"),
            use_ui,
        )
    return 0


@click.group()
@click.option(
    "--url",
    envvar="GRAFANA_URL",
    required=True,
    show_envvar=True,
    help="Grafana base URL.",
)
@click.option(
    "--token",
    envvar="GRAFANA_TOKEN",
    show_envvar=True,
    help="Bearer token.",
)
@click.option(
    "--username",
    envvar="GRAFANA_USERNAME",
    show_envvar=True,
    help="HTTP basic-auth username.",
)
@click.option(
    "--password",
    envvar="GRAFANA_PASSWORD",
    show_envvar=True,
    help="HTTP basic-auth password.",
)
@click.option(
    "--host",
    envvar="GRAFANA_HOST",
    show_envvar=True,
    help="HTTP Host header override.",
)
@click.option(
    "--sni-hostname",
    envvar="GRAFANA_SNI_HOSTNAME",
    show_envvar=True,
    help="TLS SNI hostname override.",
)
@click.option(
    "--verify/--no-verify",
    envvar="GRAFANA_VERIFY",
    default=True,
    show_default=True,
    show_envvar=True,
    help="Verify the upstream TLS certificate.",
)
@click.option(
    "--timeout",
    envvar="GRAFANA_TIMEOUT",
    type=float,
    default=60.0,
    show_default=True,
    show_envvar=True,
    help="Upstream request timeout in seconds.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    url: str,
    token: str | None,
    username: str | None,
    password: str | None,
    host: str | None,
    sni_hostname: str | None,
    verify: bool,
    timeout: float,
) -> None:
    """Query Grafana datasources and alerting resources, with API facades."""
    grafana_client = client(
        url, token, username, password, host, sni_hostname, verify, timeout
    )
    ctx.obj = grafana_client
    ctx.call_on_close(grafana_client.close)


def run_command(result: int) -> None:
    if result:
        raise Exit(result)


@cli.command("list")
@click.option("--type", "datasource_type", help="Filter by datasource type.")
@click.pass_obj
def list_command(c: httpx.Client, datasource_type: str | None) -> None:
    """List datasources."""
    run_command(cmd_list(c, SimpleNamespace(type=datasource_type)))


@cli.command("metrics")
@click.option("--uid", required=True, help="Datasource UID.")
@click.option(
    "--match",
    "matches",
    multiple=True,
    help="Series selector; repeat as needed.",
)
@click.option("--from", "start", help="Start time as RFC3339 or Unix time.")
@click.option("--to", "end", help="End time as RFC3339 or Unix time.")
@click.option("--grep", help="Client-side regular expression filter.")
@click.option("--limit", type=int, default=0, show_default=True)
@click.pass_obj
def metrics_command(
    c: httpx.Client,
    uid: str,
    matches: tuple[str, ...],
    start: str | None,
    end: str | None,
    grep: str | None,
    limit: int,
) -> None:
    """List Prometheus metric names."""
    run_command(
        cmd_metrics(
            c,
            SimpleNamespace(
                uid=uid,
                match=matches,
                start=start,
                end=end,
                grep=grep,
                limit=limit,
            ),
        )
    )


@cli.command("alert-rules")
@click.option("--folder-uid", help="Exact folder UID.")
@click.option("--group", multiple=True, help="Exact rule-group name; repeatable.")
@click.option("--rule", multiple=True, help="Exact rule title; repeatable.")
@click.option("--uid", multiple=True, help="Exact rule UID; repeatable.")
@click.option("--title", help="Case-insensitive rule-title substring.")
@click.option("--search-group", help="Case-insensitive group-name substring.")
@click.option("--search-folder", help="Case-insensitive folder-name substring.")
@click.option("--receiver", help="Receiver/contact-point name.")
@click.option("--datasource-uid", multiple=True, help="Datasource UID; repeatable.")
@click.option(
    "--state",
    multiple=True,
    type=click.Choice(
        (
            "normal",
            "inactive",
            "pending",
            "alerting",
            "firing",
            "nodata",
            "error",
            "recovering",
        )
    ),
    help="Rule state; repeatable.",
)
@click.option(
    "--health",
    multiple=True,
    type=click.Choice(("ok", "error", "nodata")),
    help="Rule health; repeatable.",
)
@click.option(
    "--type",
    "rule_type",
    type=click.Choice(("alerting", "recording")),
    help="Rule type.",
)
@click.option("--dashboard-uid", help="Dashboard UID.")
@click.option("--panel-id", type=int, help="Panel ID; requires --dashboard-uid.")
@click.option(
    "--label-matcher",
    multiple=True,
    help='JSON rule-label matcher, e.g. {"type":0,"name":"severity","value":"critical"}; repeatable.',
)
@click.option("--plugins", type=click.Choice(("hide", "only")))
@click.option("--group-limit", type=click.IntRange(min=0))
@click.option("--rule-limit", type=click.IntRange(min=0))
@click.option("--next-token", help="groupNextToken from a previous response.")
@click.option(
    "--limit-alerts",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="Maximum alert instances per rule.",
)
@click.pass_obj
def alert_rules_command(
    c: httpx.Client,
    folder_uid: str | None,
    group: tuple[str, ...],
    rule: tuple[str, ...],
    uid: tuple[str, ...],
    title: str | None,
    search_group: str | None,
    search_folder: str | None,
    receiver: str | None,
    datasource_uid: tuple[str, ...],
    state: tuple[str, ...],
    health: tuple[str, ...],
    rule_type: str | None,
    dashboard_uid: str | None,
    panel_id: int | None,
    label_matcher: tuple[str, ...],
    plugins: str | None,
    group_limit: int | None,
    rule_limit: int | None,
    next_token: str | None,
    limit_alerts: int,
) -> None:
    """Query Grafana-managed alert rules and their runtime state."""
    run_command(cmd_alert_rules(c, SimpleNamespace(**locals())))


@cli.group("alert-rule")
def alert_rule_group() -> None:
    """Manage editable App Platform alert rules."""


@alert_rule_group.command("get")
@click.argument("name")
@click.option("--namespace", default="default", show_default=True)
@click.pass_obj
def alert_rule_get_command(c: httpx.Client, name: str, namespace: str) -> None:
    """Get one editable App Platform alert rule as JSON."""
    run_command(cmd_alert_rule_get(c, SimpleNamespace(**locals())))


@alert_rule_group.command("create")
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
)
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_create_command(
    c: httpx.Client,
    file: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Create a grouped alert rule from a JSON or YAML App Platform resource."""
    run_command(cmd_alert_rule_create(c, SimpleNamespace(**locals())))


@alert_rule_group.command("reconcile-explore-links")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--datasource-uid",
    multiple=True,
    help="Only reconcile alerts using this datasource UID; repeat as needed.",
)
@click.option(
    "--check",
    is_flag=True,
    help="Make no changes and fail if an Explore link is stale or missing.",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Apply changes; without this option the command only previews them.",
)
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_reconcile_explore_links_command(
    c: httpx.Client,
    namespace: str,
    datasource_uid: tuple[str, ...],
    check: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Reconcile generated Explore links for Elasticsearch alert rules."""
    run_command(cmd_alert_rule_reconcile_explore_links(c, SimpleNamespace(**locals())))


@alert_rule_group.command("replace")
@click.argument("name")
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
)
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_replace_command(
    c: httpx.Client,
    name: str,
    file: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Replace an alert rule from a JSON or YAML App Platform resource."""
    run_command(cmd_alert_rule_replace(c, SimpleNamespace(**locals())))


@alert_rule_group.command("patch")
@click.argument("name")
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
)
@click.option(
    "--type",
    "patch_type",
    type=click.Choice(tuple(ALERT_RULE_PATCH_CONTENT_TYPES)),
    default="merge",
    show_default=True,
)
@click.option("--field-manager", default="grafana-query", show_default=True)
@click.option("--force", is_flag=True, help="Take field ownership for apply patches.")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_patch_command(
    c: httpx.Client,
    name: str,
    file: str,
    patch_type: str,
    field_manager: str,
    force: bool,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Patch an alert rule with merge, JSON, or server-side apply."""
    run_command(cmd_alert_rule_patch(c, SimpleNamespace(**locals())))


@alert_rule_group.command("edit")
@click.argument("name")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_edit_command(
    c: httpx.Client,
    name: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Edit one alert rule in $EDITOR, show a diff, and update it."""
    run_command(cmd_alert_rule_edit(c, SimpleNamespace(**locals())))


@alert_rule_group.command("delete")
@click.argument("name")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_delete_command(
    c: httpx.Client,
    name: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Delete one alert rule."""
    run_command(cmd_alert_rule_delete(c, SimpleNamespace(**locals())))


@cli.command("show")
@click.argument("resource", type=click.Choice(SHOW_RESOURCES))
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--name",
    help="Exact App Platform resource name, or folder UID.",
)
@click.option("--limit", type=click.IntRange(min=1), default=1000, show_default=True)
@click.option("--continue-token", help="App Platform list continuation token.")
@click.option("--field-selector", help="App Platform field selector.")
@click.option("--label-selector", help="App Platform label selector.")
@click.option("--query", help="Team-name search query.")
@click.option("--page", type=click.IntRange(min=1), default=1, show_default=True)
@click.pass_obj
def show_command(
    c: httpx.Client,
    resource: str,
    namespace: str,
    name: str | None,
    limit: int,
    continue_token: str | None,
    field_selector: str | None,
    label_selector: str | None,
    query: str | None,
    page: int,
) -> None:
    """Show an allow-listed read-only Grafana resource as JSON."""
    run_command(cmd_show(c, SimpleNamespace(**locals())))


@cli.command("folders")
@click.option("--uid", help="Show only this folder subtree.")
@click.option(
    "--depth",
    type=click.IntRange(min=0),
    help="Maximum child-folder depth; omit for the complete subtree.",
)
@click.option("--dashboards", is_flag=True, help="Include dashboards as leaves.")
@click.option("--json", "json_output", is_flag=True, help="Output nested JSON.")
@click.pass_obj
def folders_command(
    c: httpx.Client,
    uid: str | None,
    depth: int | None,
    dashboards: bool,
    json_output: bool,
) -> None:
    """Explore the dashboard folder hierarchy."""
    run_command(cmd_folders(c, SimpleNamespace(**locals())))


@cli.command("query")
@click.option("--uid", help="Datasource UID.")
@click.option("--expr", help="Prometheus or Loki expression.")
@click.option("--sql", help="Raw SQL.")
@click.option("--lucene", help="Elasticsearch Lucene query.")
@click.option(
    "--agg",
    type=click.Choice(("logs", "count")),
    default="logs",
    show_default=True,
)
@click.option("--limit", type=int, default=100, show_default=True)
@click.option("--time-field", default="@timestamp", show_default=True)
@click.option(
    "--target",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
    help="Panel target JSON file or - for standard input.",
)
@click.option("--from", "start", default="now-5m", show_default=True)
@click.option("--to", "end", default="now", show_default=True)
@click.option("--instant", is_flag=True, help="Run an instant query.")
@click.option("--step", help="Range step, such as 30s, 1m, or 500ms.")
@click.pass_obj
def query_command(
    c: httpx.Client,
    uid: str | None,
    expr: str | None,
    sql: str | None,
    lucene: str | None,
    agg: str,
    limit: int,
    time_field: str,
    target: str | None,
    start: str,
    end: str,
    instant: bool,
    step: str | None,
) -> None:
    """Run one datasource query."""
    run_command(
        cmd_query(
            c,
            SimpleNamespace(
                uid=uid,
                expr=expr,
                sql=sql,
                lucene=lucene,
                agg=agg,
                limit=limit,
                time_field=time_field,
                target=target,
                start=start,
                end=end,
                instant=instant,
                step=step,
            ),
        )
    )


@cli.command("prom-api")
@click.option("--uid", required=True, help="Prometheus datasource UID.")
@click.option("--listen", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=19090, show_default=True)
@click.option("--no-type-check", is_flag=True)
@click.option("--no-ui", is_flag=True, help="Disable the live terminal dashboard.")
@click.option("--quiet", is_flag=True)
@click.pass_obj
def prom_api_command(
    c: httpx.Client,
    uid: str,
    listen: str,
    port: int,
    no_type_check: bool,
    no_ui: bool,
    quiet: bool,
) -> None:
    """Serve a local Prometheus API facade backed by Grafana."""
    run_command(
        cmd_prom_api(
            c,
            SimpleNamespace(
                uid=uid,
                listen=listen,
                port=port,
                no_type_check=no_type_check,
                no_ui=no_ui,
                quiet=quiet,
            ),
        )
    )


@cli.command("query-api")
@click.option(
    "--uid",
    multiple=True,
    required=True,
    help="Allowed datasource UID; repeat as needed.",
)
@click.option(
    "--elasticsearch-uid",
    multiple=True,
    help="Read-only Elasticsearch datasource UID; repeat as needed.",
)
@click.option("--rqlite-uid", help="Read-only rqlite datasource UID.")
@click.option(
    "--prometheus-uid",
    multiple=True,
    help="Prometheus datasource UID; repeat as needed.",
)
@click.option("--listen", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=19080, show_default=True)
@click.option(
    "--max-body-bytes",
    type=int,
    default=DEFAULT_QUERY_API_MAX_BODY_BYTES,
    show_default=True,
)
@click.option(
    "--cors-origin",
    multiple=True,
    default=("http://localhost:3000", "http://127.0.0.1:3000"),
    show_default=True,
    help="Allowed browser origin; repeat as needed.",
)
@click.option("--no-uid-check", is_flag=True)
@click.option("--no-ui", is_flag=True, help="Disable the live terminal dashboard.")
@click.option("--quiet", is_flag=True)
@click.pass_obj
def query_api_command(
    c: httpx.Client,
    uid: tuple[str, ...],
    elasticsearch_uid: tuple[str, ...],
    rqlite_uid: str | None,
    prometheus_uid: tuple[str, ...],
    listen: str,
    port: int,
    max_body_bytes: int,
    cors_origin: tuple[str, ...],
    no_uid_check: bool,
    no_ui: bool,
    quiet: bool,
) -> None:
    """Serve an allow-listed local Grafana query API."""
    run_command(
        cmd_query_api(
            c,
            SimpleNamespace(
                uid=uid,
                elasticsearch_uid=elasticsearch_uid,
                rqlite_uid=rqlite_uid,
                prometheus_uid=prometheus_uid,
                listen=listen,
                port=port,
                max_body_bytes=max_body_bytes,
                cors_origin=cors_origin,
                no_uid_check=no_uid_check,
                no_ui=no_ui,
                quiet=quiet,
            ),
        )
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
