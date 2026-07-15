"""Query Grafana datasources and expose optional local API facades."""

from __future__ import annotations

import contextlib
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import sys
from urllib.parse import quote, unquote, urlsplit
import uuid
from types import SimpleNamespace
from typing import Any, cast

import httpx
import rich_click as click
from click.exceptions import Exit

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


def is_client_disconnect(e: BaseException) -> bool:
    if isinstance(e, (BrokenPipeError, ConnectionResetError)):
        return True
    return isinstance(e, OSError) and e.errno in CLIENT_DISCONNECT_ERRNOS


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

    def _handle_safely(self, options_only: bool = False) -> None:
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
            if not self.quiet:
                self.log_error("client disconnected before response completed: %s", e)

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

        return self.grafana_client.request(
            self.command,
            proxy_path,
            content=content if self.command == "POST" else None,
            headers=headers,
            extensions=REQUEST_EXTENSIONS,
        )

    def _write_upstream_response(self, upstream: httpx.Response) -> None:
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
        self.send_response(status)
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _write_text(self, status: int, body: str) -> None:
        raw = body.encode("utf-8")
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
            upstream = self.grafana_client.post(
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
        try:
            upstream = self.grafana_client.request(
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
        try:
            upstream = self.grafana_client.request(
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
        try:
            upstream = self.grafana_client.request(
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

        requested_uids: set[str] = set()
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
            requested_uids.add(uid.strip())

        denied = sorted(requested_uids - self.allowed_uids)
        if denied:
            raise QueryApiValidationError(
                403,
                f"datasource UID not allowed: {', '.join(denied)}",
            )
        return content


def cmd_prom_api(c: httpx.Client, args: Any) -> int:
    if not args.no_type_check:
        ds_type = ds_type_for(c, args.uid)
        if ds_type != "prometheus":
            raise click.UsageError(
                f"prom-api: datasource {args.uid!r} has type {ds_type!r}, not 'prometheus'"
            )

    class Handler(PrometheusApiProxyHandler):
        grafana_client = c
        uid = args.uid
        quiet = args.quiet

    addr = (args.listen, args.port)
    with ThreadingHTTPServer(addr, Handler) as server:
        host = args.listen
        if host == "0.0.0.0":
            host = "127.0.0.1"
        print(
            f"Serving Grafana-backed Prometheus API for {args.uid} at http://{host}:{args.port}",
            file=sys.stderr,
        )
        print(
            "Forwarding /api/v1/... via Grafana datasource proxy; Ctrl-C stops the server.",
            file=sys.stderr,
        )
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()
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

    class Handler(GrafanaQueryApiProxyHandler):
        grafana_client = c
        allowed_uids = allowed_uid_set
        cors_origins = frozenset(args.cors_origin)
        prometheus_uids = configured_prometheus_uids
        elasticsearch_uids = configured_elasticsearch_uids
        rqlite_uid = configured_rqlite_uid
        max_body_bytes = args.max_body_bytes
        quiet = args.quiet

    addr = (args.listen, args.port)
    with ThreadingHTTPServer(addr, Handler) as server:
        display_host = "127.0.0.1" if args.listen == "0.0.0.0" else args.listen
        print(
            f"Serving Grafana query API at http://{display_host}:{args.port}/api/ds/query",
            file=sys.stderr,
        )
        if datasource_types:
            allowed = ", ".join(
                f"{uid} ({datasource_types[uid]})" for uid in sorted(datasource_types)
            )
        else:
            allowed = ", ".join(sorted(allowed_uid_set))
        print(f"Allowed datasource UIDs: {allowed}", file=sys.stderr)
        if configured_rqlite_uid:
            print(
                f"Serving read-only rqlite facade at http://{display_host}:{args.port}/rqlite",
                file=sys.stderr,
            )
        for uid in sorted(configured_elasticsearch_uids):
            print(
                "Serving read-only Elasticsearch facade for "
                f"{uid} at http://{display_host}:{args.port}/elasticsearch/{quote(uid, safe='')}",
                file=sys.stderr,
            )
        for uid in sorted(configured_prometheus_uids):
            print(
                "Serving Prometheus facade for "
                f"{uid} at http://{display_host}:{args.port}/prometheus/{quote(uid, safe='')}",
                file=sys.stderr,
            )
        if args.listen not in ("127.0.0.1", "::1", "localhost"):
            print(
                "Warning: query-api is reachable beyond loopback; restrict it with a host firewall or Docker network.",
                file=sys.stderr,
            )
        print("Ctrl-C stops the server.", file=sys.stderr)
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()
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
@click.option("--quiet", is_flag=True)
@click.pass_obj
def prom_api_command(
    c: httpx.Client,
    uid: str,
    listen: str,
    port: int,
    no_type_check: bool,
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
                quiet=quiet,
            ),
        )
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
