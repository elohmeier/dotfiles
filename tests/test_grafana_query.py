from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
import json
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

import httpx
from click.exceptions import UsageError
from rich.console import Console

from scripts.grafana_query import (
    GrafanaQueryApiProxyHandler,
    ProxyStats,
    RequestSample,
    cmd_alert_rule_create,
    cmd_alert_rule_delete,
    cmd_alert_rule_edit,
    cmd_alert_rule_patch,
    cmd_alert_rules,
    cmd_show,
    client,
    percentile,
    render_dashboard,
)


def alert_rule(
    name: str = "rule-1",
    resource_version: str = "7",
    provenance: str = "",
) -> dict:
    return {
        "apiVersion": "rules.alerting.grafana.app/v0alpha1",
        "kind": "AlertRule",
        "metadata": {
            "name": name,
            "namespace": "default",
            "uid": "server-generated-uid",
            "resourceVersion": resource_version,
            "labels": {
                "grafana.app/folder": "folder-1",
                "grafana.com/group": "group-1",
            },
            "annotations": {
                "grafana.app/folder": "folder-1",
                "grafana.app/updatedBy": "user-1",
                "grafana.app/updatedTimestamp": "2026-08-20T10:00:00Z",
                "grafana.com/provenance": provenance,
            },
        },
        "spec": {
            "title": "Original title",
            "trigger": {"interval": "1m"},
            "noDataState": "NoData",
            "execErrState": "Error",
            "expressions": {
                "A": {
                    "relativeTimeRange": {"from": "10m0s", "to": "0s"},
                    "datasourceUID": "prometheus-1",
                    "model": {"refId": "A"},
                },
                "C": {
                    "queryType": "expression",
                    "model": {"refId": "C", "type": "threshold"},
                    "source": True,
                },
            },
        },
        "status": {"operatorStates": {}},
    }


class ClientTest(unittest.TestCase):
    def test_configures_basic_auth(self) -> None:
        with patch("scripts.grafana_query.httpx.Client") as client_class:
            client(
                "https://grafana.invalid",
                None,
                "alice",
                "secret",
                None,
                None,
                True,
                60,
            )

        auth = client_class.call_args.kwargs["auth"]
        request = next(auth.sync_auth_flow(httpx.Request("GET", "https://x.invalid")))
        self.assertEqual(request.headers["Authorization"], "Basic YWxpY2U6c2VjcmV0")

    def test_rejects_mixed_or_incomplete_auth(self) -> None:
        with self.assertRaisesRegex(UsageError, "cannot be combined"):
            client(
                "https://grafana.invalid",
                "token",
                "alice",
                "secret",
                None,
                None,
                True,
                60,
            )
        with self.assertRaisesRegex(UsageError, "requires both"):
            client(
                "https://grafana.invalid",
                None,
                "alice",
                None,
                None,
                None,
                True,
                60,
            )


class AlertRuleManagementTest(unittest.TestCase):
    def test_create_uses_grouped_provisioning_api_and_returns_app_rule(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(201, json=alert_rule())

        grafana = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        try:
            with (
                patch(
                    "scripts.grafana_query.load_document",
                    return_value=alert_rule(),
                ),
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                result = cmd_alert_rule_create(
                    grafana,
                    SimpleNamespace(
                        namespace="default",
                        file="rule.yaml",
                        dry_run=False,
                        yes=True,
                        allow_managed=False,
                    ),
                )
        finally:
            grafana.close()

        self.assertEqual(result, 0)
        self.assertEqual([r.method for r in requests], ["POST", "GET"])
        self.assertEqual(requests[0].url.path, "/api/v1/provisioning/alert-rules")
        self.assertEqual(requests[0].headers["X-Disable-Provenance"], "true")
        body = json.loads(requests[0].content)
        self.assertEqual(body["uid"], "rule-1")
        self.assertEqual(body["folderUID"], "folder-1")
        self.assertEqual(body["ruleGroup"], "group-1")
        self.assertEqual(body["condition"], "C")
        self.assertEqual(body["data"][0]["relativeTimeRange"]["from"], 600)
        self.assertEqual(body["data"][1]["datasourceUid"], "__expr__")

    def test_create_dry_run_sends_no_request(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(500)

        grafana = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        try:
            with (
                patch("scripts.grafana_query.load_document", return_value=alert_rule()),
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                result = cmd_alert_rule_create(
                    grafana,
                    SimpleNamespace(
                        namespace="default",
                        file="rule.yaml",
                        dry_run=True,
                        yes=False,
                        allow_managed=False,
                    ),
                )
        finally:
            grafana.close()

        self.assertEqual(result, 0)
        self.assertEqual(requests, [])

    def test_edit_preserves_resource_version_and_shows_diff(self) -> None:
        requests: list[httpx.Request] = []
        current = alert_rule()

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json=current)
            return httpx.Response(200, json=current)

        def edit_rule(text: str, extension: str) -> str:
            self.assertEqual(extension, ".json")
            body = json.loads(text)
            body["spec"]["title"] = "Updated title"
            return json.dumps(body, indent=2) + "\n"

        grafana = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        output = StringIO()
        try:
            with (
                patch("scripts.grafana_query.click.edit", side_effect=edit_rule),
                redirect_stdout(StringIO()),
                redirect_stderr(output),
            ):
                result = cmd_alert_rule_edit(
                    grafana,
                    SimpleNamespace(
                        namespace="default",
                        name="rule-1",
                        dry_run=False,
                        yes=True,
                        allow_managed=False,
                    ),
                )
        finally:
            grafana.close()

        self.assertEqual(result, 0)
        self.assertEqual([r.method for r in requests], ["GET", "PUT"])
        body = json.loads(requests[-1].content)
        self.assertEqual(body["metadata"]["resourceVersion"], "7")
        self.assertEqual(body["spec"]["title"], "Updated title")
        self.assertNotIn("uid", body["metadata"])
        self.assertNotIn("status", body)
        self.assertIn("Original title", output.getvalue())
        self.assertIn("Updated title", output.getvalue())

    def test_merge_patch_adds_resource_version(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=alert_rule())

        grafana = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        try:
            with (
                patch(
                    "scripts.grafana_query.load_document",
                    return_value={"spec": {"title": "Updated title"}},
                ),
                redirect_stdout(StringIO()),
            ):
                result = cmd_alert_rule_patch(
                    grafana,
                    SimpleNamespace(
                        namespace="default",
                        name="rule-1",
                        file="patch.yaml",
                        patch_type="merge",
                        field_manager="grafana-query",
                        force=False,
                        dry_run=True,
                        yes=False,
                        allow_managed=False,
                    ),
                )
        finally:
            grafana.close()

        self.assertEqual(result, 0)
        self.assertEqual([r.method for r in requests], ["GET"])

    def test_refuses_managed_rule(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=alert_rule(provenance="file"))

        grafana = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        try:
            with self.assertRaisesRegex(UsageError, "provenance file"):
                cmd_alert_rule_delete(
                    grafana,
                    SimpleNamespace(
                        namespace="default",
                        name="rule-1",
                        dry_run=False,
                        yes=True,
                        allow_managed=False,
                    ),
                )
        finally:
            grafana.close()

        self.assertEqual([r.method for r in requests], ["GET"])


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


class AlertRulesTest(unittest.TestCase):
    def test_forwards_filters_and_prints_response(self) -> None:
        requests: list[httpx.Request] = []
        body = {"status": "success", "data": {"groups": []}}

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=body)

        client = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        output = StringIO()
        try:
            with redirect_stdout(output):
                result = cmd_alert_rules(
                    client,
                    SimpleNamespace(
                        folder_uid="folder-1",
                        group=("group-a", "group-b"),
                        rule=("rule-a",),
                        uid=("uid-a",),
                        title="latency",
                        search_group=None,
                        search_folder=None,
                        receiver="on-call",
                        datasource_uid=("prom-a", "prom-b"),
                        state=("firing", "pending"),
                        health=("error",),
                        rule_type="alerting",
                        dashboard_uid="dashboard-a",
                        panel_id=3,
                        label_matcher=(
                            '{"type":0,"name":"severity","value":"critical"}',
                        ),
                        plugins="hide",
                        group_limit=10,
                        rule_limit=20,
                        next_token="next-page",
                        limit_alerts=0,
                    ),
                )
        finally:
            client.close()

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), body)
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.url.path, "/api/prometheus/grafana/api/v1/rules")
        self.assertEqual(
            request.url.params.get_list("rule_group"), ["group-a", "group-b"]
        )
        self.assertEqual(
            request.url.params.get_list("datasource_uid"), ["prom-a", "prom-b"]
        )
        self.assertEqual(request.url.params.get_list("state"), ["firing", "pending"])
        self.assertEqual(request.url.params["panel_id"], "3")
        self.assertEqual(request.url.params["limit_alerts"], "0")


class ShowTest(unittest.TestCase):
    def test_app_resource_alias_and_list_options(self) -> None:
        requests: list[httpx.Request] = []
        body = {"kind": "ReceiverList", "items": []}

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=body)

        client = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        output = StringIO()
        try:
            with redirect_stdout(output):
                result = cmd_show(
                    client,
                    SimpleNamespace(
                        resource="endpoints",
                        namespace="default",
                        name=None,
                        limit=50,
                        continue_token="next-page",
                        field_selector="spec.title=operations",
                        label_selector="provisioned=true",
                        query=None,
                        page=1,
                    ),
                )
        finally:
            client.close()

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), body)
        request = requests[0]
        self.assertEqual(
            request.url.path,
            "/apis/notifications.alerting.grafana.app/v1beta1/namespaces/default/receivers",
        )
        self.assertEqual(request.url.params["limit"], "50")
        self.assertEqual(request.url.params["continue"], "next-page")
        self.assertEqual(request.url.params["fieldSelector"], "spec.title=operations")
        self.assertEqual(request.url.params["labelSelector"], "provisioned=true")

    def test_team_search_options(self) -> None:
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"totalCount": 0, "teams": []})

        client = httpx.Client(
            base_url="https://grafana.invalid",
            transport=httpx.MockTransport(respond),
        )
        try:
            with redirect_stdout(StringIO()):
                result = cmd_show(
                    client,
                    SimpleNamespace(
                        resource="teams",
                        namespace="default",
                        name=None,
                        limit=25,
                        continue_token=None,
                        field_selector=None,
                        label_selector=None,
                        query="platform",
                        page=2,
                    ),
                )
        finally:
            client.close()

        self.assertEqual(result, 0)
        request = requests[0]
        self.assertEqual(request.url.path, "/api/teams/search")
        self.assertEqual(
            dict(request.url.params),
            {"page": "2", "perpage": "25", "query": "platform"},
        )


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
