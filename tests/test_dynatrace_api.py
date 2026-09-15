import os
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import httpx

from scripts import dynatrace_api


TOKEN = "test-token"


def config(**changes):
    values = {
        "url": "https://127.0.0.1:9999",
        "host": "dynatrace.example.test",
        "environment_id": "environment-id",
        "token_command": None,
        "verify": False,
        "timeout": 60,
    }
    values.update(changes)
    return dynatrace_api.Config(**values)


def response(content: bytes = b"{}", content_type: str = "application/json"):
    return httpx.Response(
        200,
        content=content,
        headers={"content-type": content_type},
        request=httpx.Request("GET", "https://example.test"),
    )


def test_environment_and_cluster_paths():
    cfg = config()
    assert dynatrace_api.endpoint_path(cfg, "api/v2/metrics") == (
        "/e/environment-id/api/v2/metrics"
    )
    assert dynatrace_api.endpoint_path(cfg, "api/cluster/v2/environments") == (
        "/api/cluster/v2/environments"
    )
    assert dynatrace_api.endpoint_path(cfg, "api/v2/metrics", cluster=True) == (
        "/api/v2/metrics"
    )


def test_token_command_reads_first_line():
    cfg = config(token_command="secret-tool token")
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(
            dynatrace_api.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, TOKEN + "\nnotes\n", ""),
        ) as run,
    ):
        assert dynatrace_api.token(cfg) == TOKEN
    assert run.call_args.args[0] == ["secret-tool", "token"]


def test_request_uses_host_for_header_and_sni():
    client = MagicMock()
    client.__enter__.return_value.request.return_value = response()
    with (
        patch.object(dynatrace_api.httpx, "Client", return_value=client) as factory,
        patch.dict(os.environ, {"DYNATRACE_TOKEN": TOKEN}),
    ):
        dynatrace_api.request(
            config(), "GET", "api/v2/metrics?scope=builtin", params=("pageSize=5",)
        )
    assert factory.call_args.kwargs["base_url"] == "https://127.0.0.1:9999"
    assert factory.call_args.kwargs["headers"]["Host"] == "dynatrace.example.test"
    call = client.__enter__.return_value.request.call_args
    assert call.args[1] == "/e/environment-id/api/v2/metrics?scope=builtin&pageSize=5"
    assert call.kwargs["extensions"] == {"sni_hostname": "dynatrace.example.test"}


def test_cli_maps_repeated_params_to_the_request_layer():
    with patch.object(dynatrace_api, "request") as request:
        result = CliRunner().invoke(
            dynatrace_api.main,
            ["get", "api/v2/metrics", "--param", "pageSize=5"],
            env={"DYNATRACE_URL": "https://example.test"},
        )
    assert result.exit_code == 0
    assert request.call_args.kwargs["params"] == ("pageSize=5",)


def test_raw_body_and_file_body(tmp_path: Path):
    payload = tmp_path / "payload.json"
    payload.write_text('{"enabled": true}')
    assert dynatrace_api.body(None, str(payload), False) == ({"enabled": True}, None)
    assert dynatrace_api.body("plain text", None, True) == (None, b"plain text")
