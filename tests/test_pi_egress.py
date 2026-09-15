"""Proxy regressions. Run with mitmproxy 12.2.3; Docker tests opt in via
PI_EGRESS_TEST_IMAGE=pi-less-yolo-proxy:egress-test.
"""

import concurrent.futures
import hashlib
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


def test_layered_policy_deny_precedence_and_snapshot_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(egress, "STATE_DIR", str(tmp_path))
    (tmp_path / "config").write_text("allow=provider.test\n")
    (tmp_path / "rules.allow").write_text("global.test:443\n")
    (tmp_path / "project.allow").write_text("project.test:443\nblocked.test:443\n")
    (tmp_path / "rules.deny").write_text("blocked.test:443\n")
    (tmp_path / "project.deny").write_text("global.test:443\n")
    policy = egress.load_policy()
    assert egress.check_rules(policy, "blocked.test", 443) == "deny"
    assert egress.check_rules(policy, "global.test", 443) == "deny"
    assert egress.check_rules(policy, "project.test", 443) == "project.test:443"
    assert egress.check_rules(policy, "provider.test", 443) == "provider.test"
    (tmp_path / "mise.toml").write_text('[env]\nPI_EGRESS_ALLOW="agent.test:443"\n')
    assert egress.check_rules(egress.load_policy(), "agent.test", 443) is None


def test_build_forwards_ca_to_both_images(tmp_path):
    runtime = tmp_path / "docker"
    runtime.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$BUILD_LOG"\n')
    runtime.chmod(0o755)
    ca = tmp_path / "ca.pem"
    ca.write_text("test CA bundle\n")
    (tmp_path / "config.json").write_text("{}\n")
    log = tmp_path / "build.log"
    env = dict(
        os.environ,
        PI_CONTAINER_RUNTIME=str(runtime),
        PI_CA_CERT=str(ca),
        MISE_TASK_DIR=str(TASKS),
        DOCKER_CONFIG=str(tmp_path),
        BUILD_LOG=str(log),
    )
    run("bash", str(TASKS / "executable_build"), env=env)
    arguments = log.read_text().splitlines()
    assert arguments.count(f"id=extra_ca,src={ca}") == 2
    assert sum(argument.startswith("CA_ID=") for argument in arguments) == 2


def test_saved_web_url_without_runtime(tmp_path):
    saved = tmp_path / "web-url"
    saved.write_text("http://172.18.0.2:8081/egress?token=test-token\n")
    env = dict(
        os.environ,
        PI_EGRESS_DIR=str(tmp_path),
        PI_EGRESS_WEB_PORT="18081",
        PI_CONTAINER_RUNTIME="/does-not-exist",
    )
    expected = "http://127.0.0.1:18081/egress?token=test-token"
    assert run("bash", str(TASKS / "executable_egress"), "url", env=env) == expected
    assert saved.read_text().strip() == expected
    assert saved.stat().st_mode & 0o777 == 0o600
    del env["PI_EGRESS_WEB_PORT"]
    assert run("bash", str(TASKS / "executable_egress"), "url", env=env) == expected


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    image = os.environ.get("PI_EGRESS_TEST_IMAGE")
    if not image:
        pytest.skip("Set PI_EGRESS_TEST_IMAGE to run Docker integration tests")
    state = tmp_path_factory.mktemp("pi-egress")
    name = "pi-egress-test-" + uuid.uuid4().hex[:8]
    upstream = name + "-upstream"
    trusted_image = name + ":trusted"
    run(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(state / "root.key"),
        "-out",
        str(state / "root.pem"),
        "-subj",
        "/CN=Pi egress test root",
        "-days",
        "1",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
    )
    run(
        "openssl",
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(state / "server.key"),
        "-out",
        str(state / "server.csr"),
        "-subj",
        f"/CN={upstream}",
    )
    (state / "server.ext").write_text(
        f"subjectAltName=DNS:{upstream}\nextendedKeyUsage=serverAuth\n"
    )
    run(
        "openssl",
        "x509",
        "-req",
        "-in",
        str(state / "server.csr"),
        "-CA",
        str(state / "root.pem"),
        "-CAkey",
        str(state / "root.key"),
        "-CAcreateserial",
        "-out",
        str(state / "server.pem"),
        "-days",
        "1",
        "-extfile",
        str(state / "server.ext"),
    )
    (state / "secrets.rules").write_text(
        f"TOKEN hosts={upstream}:8000,{upstream}:8443 methods=GET\n"
    )
    (state / "mitmproxy").mkdir()
    env = dict(
        os.environ,
        PI_EGRESS_DIR=str(state),
        PI_EGRESS_NAME=name,
        PI_EGRESS_SUBNET="10.225.0.0/24",
        PI_EGRESS_PROXY_IP="10.225.0.2",
        PI_PROXY_IMAGE=trusted_image,
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
            "docker",
            "build",
            "-q",
            "-t",
            trusted_image,
            "--secret",
            f"id=extra_ca,src={state / 'root.pem'}",
            "--build-arg",
            f"CA_ID={name}",
            str(PROXY),
        )
        run(
            "bash",
            "-c",
            'set -euo pipefail; source "$1/_egress"; egress_write_config interactive; egress_prepare_secrets; egress_ensure_proxy',
            "test",
            str(TASKS),
            env=env,
        )
        run("pi-egress-control", "start-bridge", "docker", proxy, env=env)
        eventually(lambda: (state / "bridge-ready").exists())
        server = """
import http.server, json, ssl, threading, time
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
plain = http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Echo)
threading.Thread(target=plain.serve_forever, daemon=True).start()
secure = http.server.ThreadingHTTPServer(("0.0.0.0", 8443), Echo)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/tls/server.pem", "/tls/server.key")
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
            "--volume",
            f"{state}/server.pem:/tls/server.pem:ro",
            "--volume",
            f"{state}/server.key:/tls/server.key:ro",
            "--entrypoint",
            "python",
            image,
            "-c",
            server,
        )
        url = (state / "web-url").read_text().strip()
        assert url.startswith("http://127.0.0.1:18081/egress?token=")
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
        subprocess.run(["docker", "image", "rm", trusted_image], capture_output=True)


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
        assert (
            client.post(
                decision, json={"choice": "allow-always", "scope": "global"}
            ).status_code
            == 200
        )
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


def test_repeated_web_prints_url_without_restarting(live):
    bin_dir = live["state"] / "bin"
    bin_dir.mkdir()
    opener = bin_dir / "open"
    opener.write_text("#!/bin/sh\nexit 0\n")
    opener.chmod(0o755)
    env = dict(
        live["env"],
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        PI_PROXY_IMAGE="pi-egress-do-not-build:missing",
    )
    del env["PI_EGRESS_WEB_PORT"]
    expected = (live["state"] / "web-url").read_text().strip()
    original = run("docker", "inspect", "-f", "{{.Id}}", live["name"] + "-proxy")
    for _ in range(2):
        assert run("bash", str(TASKS / "executable_egress"), "web", env=env) == expected
    assert (
        run("docker", "inspect", "-f", "{{.Id}}", live["name"] + "-proxy") == original
    )


def test_upstream_ca_verification(live):
    client, curl = live["client"], live["curl"]
    proxy = live["name"] + "-proxy"
    public_ca = run(
        "docker",
        "exec",
        proxy,
        "python",
        "-c",
        "import certifi; print(certifi.where())",
    )
    run(
        "docker",
        "exec",
        proxy,
        "python",
        "-c",
        "import certifi; from pathlib import Path; "
        "bundle = Path('/etc/pi-egress/upstream-ca.pem').read_bytes(); "
        "assert bundle.startswith(Path(certifi.where()).read_bytes()); "
        "assert Path('/egress/root.pem').read_bytes() in bundle",
    )
    assert client.get("/options").json()["ssl_insecure"]["value"] is False
    client.put("/options", json={"ssl_verify_upstream_trusted_ca": public_ca})
    try:
        assert "Certificate verify failed" in curl(
            f"https://{live['upstream']}:8443/untrusted"
        )
    finally:
        client.put(
            "/options",
            json={"ssl_verify_upstream_trusted_ca": "/etc/pi-egress/upstream-ca.pem"},
        )
    assert (
        json.loads(curl(f"https://{live['upstream']}:8443/trusted"))["path"]
        == "/trusted"
    )


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


def test_two_project_proxies_and_project_browser_save(live, tmp_path):
    contexts = []
    upstream = "pi-project-upstream-" + uuid.uuid4().hex[:8]
    try:
        for label in ("a", "b"):
            root = tmp_path / label
            root.mkdir()
            (root / "mise.toml").write_text("# shared team settings\n[env]\n")
            key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
            name = "pi-egress-" + key
            state = tmp_path / "state/projects" / key
            env = {
                k: v for k, v in os.environ.items() if not k.startswith("PI_EGRESS_")
            }
            env.update(
                PI_EGRESS_GLOBAL_DIR=str(tmp_path / "state"),
                PI_EGRESS_PROJECT_ROOT=str(root),
                PI_EGRESS_ALLOW="scope.test:8000" if label == "a" else "",
                PI_EGRESS_ALLOW_PRIVATE="1",
                PI_EGRESS_TIMEOUT="15",
                PI_PROXY_IMAGE=live["env"]["PI_PROXY_IMAGE"],
                DOCKER_CMD="docker",
            )
            contexts.append(dict(root=root, name=name, state=state, env=env))
            run(
                "bash",
                "-c",
                'set -euo pipefail; source "$1/_egress"; egress_write_config interactive; egress_prepare_secrets; egress_ensure_proxy; pi-egress-control start-bridge --scope project docker "$PI_EGRESS_PROXY"',
                "test",
                str(TASKS),
                env=env,
            )
        a, b = contexts
        assert (a["state"] / "web-port").read_text() != (
            b["state"] / "web-port"
        ).read_text()
        run(
            "docker",
            "run",
            "-d",
            "--name",
            upstream,
            "--network",
            a["name"] + "-external",
            "--network-alias",
            "scope.test",
            "--entrypoint",
            "python",
            live["env"]["PI_PROXY_IMAGE"],
            "-m",
            "http.server",
            "8000",
        )
        run(
            "docker",
            "network",
            "connect",
            "--alias",
            "scope.test",
            b["name"] + "-external",
            upstream,
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

        def curl(ctx):
            ip = run(
                "docker",
                "inspect",
                "-f",
                '{{(index .NetworkSettings.Networks "'
                + ctx["name"]
                + '-internal").IPAddress}}',
                ctx["name"] + "-proxy",
            )
            return run(
                "docker",
                "run",
                "--rm",
                "--network",
                ctx["name"] + "-internal",
                "--entrypoint",
                "curl",
                "pi-less-yolo:latest",
                "-sS",
                "--max-time",
                "20",
                "--proxy",
                f"http://{ip}:3128",
                "http://scope.test:8000/",
            )

        assert "Directory listing" in curl(a)
        url = (b["state"] / "web-url").read_text().strip()
        assert url.startswith("http://127.0.0.1:")
        with httpx.Client(base_url=url.split("/egress")[0], trust_env=False) as client:
            token = re.search(r'data-xsrf="([^"]+)"', client.get(url).text)
            assert token
            client.headers["X-XSRFToken"] = token[1]
            eventually(lambda: client.get("/egress/pending").json()["can_save"])
            with concurrent.futures.ThreadPoolExecutor() as pool:
                request = pool.submit(curl, b)
                pending = eventually(
                    lambda: client.get("/egress/pending").json()["requests"]
                )
                assert not list((a["state"] / "pending").iterdir())
                endpoint = f"/egress/decision/{pending[0]['id']}"
                assert (
                    client.post(
                        endpoint, json={"choice": "allow-always", "scope": "global"}
                    ).status_code
                    == 409
                )
                assert (
                    client.post(
                        endpoint, json={"choice": "allow-always", "scope": "project"}
                    ).status_code
                    == 200
                )
                assert "Directory listing" in request.result()
        assert "scope.test:8000" in (b["root"] / "mise.toml").read_text()
        assert "scope.test" not in (a["root"] / "mise.toml").read_text()
        assert not (tmp_path / "state/rules.allow").read_text().strip()
        # Global denials immediately reach both already-running proxies.
        run(
            "bash",
            str(TASKS / "executable_egress"),
            "deny",
            "--scope",
            "global",
            "scope.test:8000",
            env=b["env"],
        )
        assert "deny rule" in curl(a)
        assert "deny rule" in curl(b)
        # Allocated ports/networks are reused on a second ensure.
        before = run("docker", "inspect", "-f", "{{.Id}}", a["name"] + "-proxy")
        run(
            "bash",
            "-c",
            'set -euo pipefail; source "$1/_egress"; egress_ensure_proxy',
            "test",
            str(TASKS),
            env=a["env"],
        )
        assert run("docker", "inspect", "-f", "{{.Id}}", a["name"] + "-proxy") == before
    finally:
        subprocess.run(["docker", "rm", "-f", upstream], capture_output=True)
        for ctx in contexts:
            subprocess.run(
                ["docker", "rm", "-f", ctx["name"] + "-proxy"], capture_output=True
            )
            subprocess.run(
                [
                    "docker",
                    "network",
                    "rm",
                    ctx["name"] + "-internal",
                    ctx["name"] + "-external",
                ],
                capture_output=True,
            )
