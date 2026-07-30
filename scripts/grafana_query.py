"""Query Grafana datasources and expose optional local API facades."""

from __future__ import annotations

import contextlib
from collections import Counter, deque
from dataclasses import dataclass, field
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
console = Console(stderr=True)


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
    host: str | None,
    sni_hostname: str | None,
    verify: bool,
    timeout: float,
) -> httpx.Client:
    global REQUEST_EXTENSIONS
    REQUEST_EXTENSIONS = {"sni_hostname": sni_hostname} if sni_hostname else {}
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host:
        headers["Host"] = host
    return httpx.Client(
        base_url=url.rstrip("/"),
        headers=headers,
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
    host: str | None,
    sni_hostname: str | None,
    verify: bool,
    timeout: float,
) -> None:
    """Query Grafana datasources and expose optional local API facades."""
    grafana_client = client(url, token, host, sni_hostname, verify, timeout)
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
