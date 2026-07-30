from __future__ import annotations

from http.server import ThreadingHTTPServer
from io import StringIO
import threading
import unittest

import httpx
from rich.console import Console

from scripts.grafana_query import (
    GrafanaQueryApiProxyHandler,
    ProxyStats,
    RequestSample,
    percentile,
    render_dashboard,
)


class ProxyStatsTest(unittest.TestCase):
    def test_records_batch_usage_and_payloads(self) -> None:
        stats = ProxyStats({"prom-main": "prometheus"})
        sample = RequestSample("POST", "ds/query", 120)
        stats.begin(sample)
        sample.status = 200
        sample.response_bytes = 1_500
        sample.duration = 0.25
        sample.upstream_duration = 0.2
        sample.datasources["prom-main"] = 2
        stats.finish(sample)

        snapshot = stats.snapshot()
        self.assertEqual(snapshot.requests, 1)
        self.assertEqual(snapshot.upstream_requests, 1)
        self.assertEqual(snapshot.status_counts, {"2xx": 1})
        self.assertEqual(snapshot.request_bytes, 120)
        self.assertEqual(snapshot.response_bytes, 1_500)
        self.assertEqual(snapshot.datasources[0].requests, 1)
        self.assertEqual(snapshot.datasources[0].targets, 2)
        self.assertEqual(percentile(snapshot.latencies, 0.95), 0.25)

    def test_dashboard_treats_datasource_names_as_text(self) -> None:
        uid = "[red]prod[/red]"
        stats = ProxyStats({uid: "prometheus"})
        output = StringIO()
        render_console = Console(
            file=output,
            width=120,
            color_system=None,
        )

        render_console.print(
            render_dashboard(stats, "Grafana query API", "http://localhost", False)
        )

        self.assertIn(uid, output.getvalue())
        self.assertIn("Waiting for requests", output.getvalue())


class ProxyHandlerTest(unittest.TestCase):
    def test_query_api_records_requests_and_query_targets(self) -> None:
        upstream_bodies: list[dict] = []

        def respond(request: httpx.Request) -> httpx.Response:
            upstream_bodies.append(httpx.Response(200, content=request.content).json())
            return httpx.Response(200, json={"results": {}})

        upstream_client = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        proxy_stats = ProxyStats({"prom-main": "prometheus"})

        class Handler(GrafanaQueryApiProxyHandler):
            pass

        Handler.grafana_client = upstream_client
        Handler.allowed_uids = frozenset({"prom-main"})
        Handler.cors_origins = frozenset()
        Handler.datasource_types = {"prom-main": "prometheus"}
        Handler.stats = proxy_stats
        Handler.quiet = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/ds/query"
            queries = [
                {"datasource": {"uid": "prom-main", "type": "prometheus"}},
                {"datasource": {"uid": "prom-main", "type": "prometheus"}},
            ]
            with httpx.Client() as client:
                self.assertEqual(
                    client.post(url, json={"queries": queries}).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(url, json={"queries": []}).status_code,
                    400,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            upstream_client.close()

        snapshot = proxy_stats.snapshot()
        self.assertEqual(upstream_bodies, [{"queries": queries}])
        self.assertEqual(snapshot.requests, 2)
        self.assertEqual(snapshot.upstream_requests, 1)
        self.assertEqual(snapshot.status_counts, {"2xx": 1, "4xx": 1})
        self.assertEqual(snapshot.datasources[0].requests, 1)
        self.assertEqual(snapshot.datasources[0].targets, 2)


if __name__ == "__main__":
    unittest.main()
