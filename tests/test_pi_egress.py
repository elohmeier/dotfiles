"""Proxy regressions. Run with mitmproxy 12.2.3; Docker tests opt in via
PI_EGRESS_TEST_IMAGE=pi-less-yolo-proxy:egress-test.
"""

import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

import httpx
import pytest

pytest.importorskip("mitmproxy")
from mitmproxy import connection, http, io

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "home/dot_config/pi-less-yolo/proxy"
TASKS = ROOT / "home/dot_config/pi-less-yolo/exact_tasks/exact_pi"
spec = importlib.util.spec_from_file_location("pi_egress", PROXY / "pi_egress.py")
assert spec and spec.loader
egress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(egress)


def run(*args, **kwargs):
    return subprocess.run(
        args, check=True, capture_output=True, text=True, **kwargs
    ).stdout.strip()


def eventually(fn, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("Condition did not become true")


def test_redaction_preserves_live_request_and_clears_backup(monkeypatch):
    policy = egress.Policy()
    secret = egress.Secret(
        "TOKEN", ["example.com"], ["GET"], "pi-secret-test", "test-real-value"
    )
    policy.secrets = [secret]
    monkeypatch.setattr(egress, "load_policy", lambda: policy)
    addon = egress.PiEgress()
    flow = http.HTTPFlow(
        connection.Client(peername=("127.0.0.1", 1234), sockname=("127.0.0.1", 3128)),
        connection.Server(address=("example.com", 443)),
    )
    flow.request = http.Request.make(
        "GET",
        "https://example.com",
        headers={"Authorization": "Bearer test-real-value", "Cookie": "unscoped-value"},
    )
    flow.backup()
    copy = addon.redacted_copy(flow)
    assert copy.id == flow.id
    assert copy.request.headers["Authorization"] == "Bearer pi-secret-test"
    assert copy.request.headers["Cookie"] == "[redacted]"
    assert copy._backup is None
    assert flow.request.headers["Authorization"] == "Bearer test-real-value"


def test_recording_rotation_and_disable(tmp_path, monkeypatch):
    policy = egress.Policy()
    policy.record = True
    monkeypatch.setattr(egress, "load_policy", lambda: policy)
    path = tmp_path / "flows.mitm"
    monkeypatch.setattr(egress, "FLOWS_FILE", str(path))
    monkeypatch.setattr(egress, "RECORD_LIMIT", 1)
    addon = egress.PiEgress()
    flow = http.HTTPFlow(
        connection.Client(peername=("127.0.0.1", 1234), sockname=("127.0.0.1", 3128)),
        connection.Server(address=("example.com", 443)),
    )
    flow.request = http.Request.make("GET", "https://example.com")
    addon._record(flow)
    flow.request.path = "/second"
    addon._record(flow)
    with path.open("rb") as file:
        assert list(io.FlowReader(file).stream())[0].id == flow.id
    assert (tmp_path / "flows.mitm.1").is_file()
    before = path.read_bytes()
    policy.record = False
    addon._record(flow)
    assert path.read_bytes() == before
    addon._flow_writer.fo.close()


@pytest.mark.parametrize("record", ["0", "1"])
def test_record_boolean_and_mount_isolation(tmp_path, record):
    state = tmp_path / "state"
    env = dict(os.environ, PI_EGRESS_DIR=str(state), PI_EGRESS_RECORD=record)
    run(
        "bash",
        "-c",
        'source "$1/_egress"; egress_write_config interactive',
        "test",
        str(TASKS),
        env=env,
    )
    assert ("record=1" in (state / "config").read_text()) == (record == "1")
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1/_egress"; egress_check_mount "$2"',
            "test",
            str(TASKS),
            str(tmp_path),
        ],
        env=env,
        capture_output=True,
    )
    assert result.returncode != 0
    assert b"exposes proxy state" in result.stderr


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    image = os.environ.get("PI_EGRESS_TEST_IMAGE")
    if not image:
        pytest.skip("Set PI_EGRESS_TEST_IMAGE to run Docker integration tests")
    state = tmp_path_factory.mktemp("pi-egress")
    name = "pi-egress-test-" + uuid.uuid4().hex[:8]
    upstream = name + "-upstream"
    (state / "secrets.rules").write_text(
        f"TOKEN hosts={upstream}:8000,{upstream}:8443 methods=GET\n"
    )
    (state / "mitmproxy").mkdir()
    (state / "mitmproxy/config.yaml").write_text("ssl_insecure: true\n")
    env = dict(
        os.environ,
        PI_EGRESS_DIR=str(state),
        PI_EGRESS_NAME=name,
        PI_EGRESS_SUBNET="10.225.0.0/24",
        PI_EGRESS_PROXY_IP="10.225.0.2",
        PI_PROXY_IMAGE=image,
        DOCKER_CMD="docker",
        PI_EGRESS_WEB_PORT="18081",
        PI_EGRESS_RECORD="1",
        PI_EGRESS_INSPECT="all",
        PI_EGRESS_TIMEOUT="15",
        PI_EGRESS_ALLOW_PRIVATE="1",
        TOKEN="integration-real-secret",
    )
    proxy = name + "-proxy"
    try:
        run(
            "bash",
            "-c",
            'set -euo pipefail; source "$1/_egress"; egress_write_config interactive; egress_prepare_secrets; egress_ensure_proxy',
            "test",
            str(TASKS),
            env=env,
        )
        server = """
import http.server, json, ssl, subprocess, threading, time
class Echo(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: integration-")
            self.wfile.flush()
            time.sleep(0.1)
            self.wfile.write(b"real-secret\\n\\n")
            self.wfile.flush()
            time.sleep(2)
            self.wfile.write(b"data: done\\n\\n")
            return
        if self.path == "/slow": time.sleep(3)
        body = json.dumps(dict(headers=dict(self.headers), path=self.path)).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "/tmp/key.pem", "-out", "/tmp/cert.pem", "-subj", "/CN=test", "-days", "1"], check=True, capture_output=True)
plain = http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Echo)
threading.Thread(target=plain.serve_forever, daemon=True).start()
secure = http.server.ThreadingHTTPServer(("0.0.0.0", 8443), Echo)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/tmp/cert.pem", "/tmp/key.pem")
secure.socket = context.wrap_socket(secure.socket, server_side=True)
secure.serve_forever()
"""
        run(
            "docker",
            "run",
            "-d",
            "--name",
            upstream,
            "--network",
            name + "-external",
            "--network-alias",
            "blocked.test",
            "--entrypoint",
            "python",
            image,
            "-c",
            server,
        )
        url = re.sub(
            r"http://[^/]+",
            "http://127.0.0.1:18081",
            (state / "web-url").read_text().strip(),
        )
        client = httpx.Client(base_url="http://127.0.0.1:18081", trust_env=False)
        page = client.get(url)
        assert page.status_code == 200, page.text
        token = re.search(r'data-xsrf="([^"]+)"', page.text)
        assert token
        client.headers["X-XSRFToken"] = token[1]
        placeholder = (state / "secrets.env").read_text().split("\t")[1]

        def curl(url, *args):
            return run(
                "docker",
                "run",
                "--rm",
                "--network",
                name + "-internal",
                "--volume",
                f"{state}/mitmproxy/mitmproxy-ca-cert.pem:/ca.pem:ro",
                "--entrypoint",
                "curl",
                "pi-less-yolo:latest",
                "-sS",
                "--max-time",
                "25",
                "--cacert",
                "/ca.pem",
                "--proxy",
                "http://10.225.0.2:3128",
                *args,
                url,
            )

        eventually(
            lambda: (
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        upstream,
                        "python",
                        "-c",
                        "import socket; socket.create_connection(('127.0.0.1',8000)).close()",
                    ],
                    capture_output=True,
                ).returncode
                == 0
            )
        )
        yield dict(
            state=state,
            name=name,
            upstream=upstream,
            client=client,
            curl=curl,
            placeholder=placeholder,
            env=env,
        )
        client.close()
    finally:
        for container in (upstream, proxy):
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        for network in (name + "-internal", name + "-external"):
            subprocess.run(["docker", "network", "rm", network], capture_output=True)


def test_web_approval_and_https_recording(live):
    client, curl = live["client"], live["curl"]
    assert (
        httpx.get("http://127.0.0.1:18081/egress/pending", trust_env=False).status_code
        == 403
    )
    with concurrent.futures.ThreadPoolExecutor() as pool:
        request = pool.submit(curl, "http://blocked.test:8000/approved")
        pending = eventually(lambda: client.get("/egress/pending").json()["requests"])
        decision = f"/egress/decision/{pending[0]['id']}"
        assert client.post(decision, json={"choice": "allow-always"}).status_code == 200
        assert json.loads(request.result())["path"] == "/approved"
        assert client.post(decision, json={"choice": "allow"}).status_code == 409
    assert "blocked.test:8000" in (live["state"] / "rules.allow").read_text()
    result = curl(
        f"https://{live['upstream']}:8443/tls",
        "-H",
        f"Authorization: Bearer {live['placeholder']}",
    )
    # The echo response is redacted back to the placeholder before delivery.
    assert live["placeholder"] in result
    assert "integration-real-secret" not in result
    with (live["state"] / "flows.mitm").open("rb") as file:
        flows = list(io.FlowReader(file).stream())
    assert any(
        isinstance(flow, http.HTTPFlow) and flow.request.path == "/tls"
        for flow in flows
    )
    assert b"integration-real-secret" not in (live["state"] / "flows.mitm").read_bytes()


def test_live_redaction_and_native_editing(live):
    client, curl = live["client"], live["curl"]
    with concurrent.futures.ThreadPoolExecutor() as pool:
        request = pool.submit(
            curl,
            f"http://{live['upstream']}:8000/slow",
            "-H",
            f"Authorization: Bearer {live['placeholder']}",
        )
        flow = eventually(
            lambda: next(
                (
                    f
                    for f in client.get("/flows").json()
                    if f.get("request", {}).get("path") == "/slow"
                ),
                None,
            )
        )
        for endpoint in (
            "/flows",
            "/flows/dump",
            f"/flows/{flow['id']}/request/content.data",
        ):
            assert b"integration-real-secret" not in client.get(endpoint).content
        request.result()
        assert (
            client.put("/options", json={"intercept": "~q & ~u /edit"}).status_code
            == 200
        )
        request = pool.submit(curl, f"http://{live['upstream']}:8000/edit")
        flow = eventually(
            lambda: next(
                (f for f in client.get("/flows").json() if f["intercepted"]), None
            )
        )
        assert (
            client.put(
                f"/flows/{flow['id']}", json={"request": {"path": "/edited"}}
            ).status_code
            == 200
        )
        assert client.post(f"/flows/{flow['id']}/resume").status_code == 200
        assert json.loads(request.result())["path"] == "/edited"
        client.put("/options", json={"intercept": None})


def test_deny_expiry_and_csrf(live):
    client, curl = live["client"], live["curl"]
    with concurrent.futures.ThreadPoolExecutor() as pool:
        request = pool.submit(curl, "http://blocked.test:8001/denied")
        pending = eventually(lambda: client.get("/egress/pending").json()["requests"])
        endpoint = f"/egress/decision/{pending[0]['id']}"
        token = client.headers.pop("X-XSRFToken")
        assert client.post(endpoint, json={"choice": "allow"}).status_code == 403
        client.headers["X-XSRFToken"] = token
        assert client.post(endpoint, json={"choice": "deny-session"}).status_code == 200
        assert "denied by user" in request.result()
    assert "denied for session" in curl("http://blocked.test:8001/denied-again")
    config = live["state"] / "config"
    original = config.read_text()
    config.write_text(original.replace("timeout=15", "timeout=1"))
    try:
        assert "default deny" in curl("http://blocked.test:8002/expired")
        assert not client.get("/egress/pending").json()["requests"]
    finally:
        config.write_text(original)


def test_edit_rechecks_secret_method_scope(live):
    client, curl = live["client"], live["curl"]
    client.put("/options", json={"intercept": "~q & ~u /scope"})
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            request = pool.submit(
                curl,
                f"https://{live['upstream']}:8443/scope",
                "-H",
                f"Authorization: Bearer {live['placeholder']}",
            )
            flow = eventually(
                lambda: next(
                    (f for f in client.get("/flows").json() if f["intercepted"]), None
                )
            )
            client.put(f"/flows/{flow['id']}", json={"request": {"method": "POST"}})
            client.post(f"/flows/{flow['id']}/resume")
            assert "not permitted for POST" in request.result()
    finally:
        client.put("/options", json={"intercept": None})


def test_shell_defaults_and_stable_placeholders(live):
    env = {
        k: v
        for k, v in live["env"].items()
        if k not in ("PI_EGRESS", "PI_EGRESS_RECORD", "PI_EGRESS_INSPECT")
    }
    output = run(
        "bash",
        str(TASKS / "executable_shell"),
        env=env,
        cwd=ROOT,
        input='test "$HTTPS_PROXY" = http://10.225.0.2:3128 && test -f "$NODE_EXTRA_CA_CERTS" && echo shell-ready\nexit\n',
    )
    assert "shell-ready" in output
    config = (live["state"] / "config").read_text()
    assert (
        "mode=interactive" in config
        and "record=1" in config
        and "intercept=all" in config
    )
    assert (live["state"] / "secrets.env").read_text().split("\t")[1] == live[
        "placeholder"
    ]


def test_internal_network_cannot_reach_web(live):
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            live["name"] + "-internal",
            "--entrypoint",
            "curl",
            "pi-less-yolo:latest",
            "--noproxy",
            "*",
            "--max-time",
            "2",
            "http://10.225.0.2:8081/egress",
        ],
        capture_output=True,
    )
    assert result.returncode != 0
    external_ip = run(
        "docker",
        "inspect",
        "-f",
        '{{range .NetworkSettings.Networks}}{{if ne .IPAddress "10.225.0.2"}}{{.IPAddress}}{{end}}{{end}}',
        live["name"] + "-proxy",
    )
    (live["state"] / "rules.allow").write_text(f"{external_ip}:8081\n")
    assert "proxy administration address" in live["curl"](
        f"http://{external_ip}:8081/egress"
    )


def test_event_stream_is_incremental_and_recorded(live):
    with subprocess.Popen(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            live["name"] + "-internal",
            "--entrypoint",
            "curl",
            "pi-less-yolo:latest",
            "-sSN",
            "--max-time",
            "15",
            "--proxy",
            "http://10.225.0.2:3128",
            f"http://{live['upstream']}:8000/events",
        ],
        stdout=subprocess.PIPE,
        text=True,
    ) as process:
        assert process.stdout
        first = process.stdout.readline()
        start = time.monotonic()
        rest = process.stdout.read()
        assert time.monotonic() - start > 1
        assert process.wait() == 0
    assert first == f"data: {live['placeholder']}\n"
    assert "data: done" in rest
    with (live["state"] / "flows.mitm").open("rb") as file:
        events = [
            f
            for f in io.FlowReader(file).stream()
            if isinstance(f, http.HTTPFlow) and f.request.path == "/events"
        ]
    assert events and events[0].response
    assert b"data: done" in (events[0].response.content or b"")
