import base64
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import httpx
import pytest

from scripts import teamcity


TOKEN = "test-token-never-in-argv"


def response(content: bytes = b'{"count":0}', content_type: str = "application/json"):
    return httpx.Response(
        200,
        content=content,
        headers={"content-type": content_type},
        request=httpx.Request("GET", "https://example.test"),
    )


def invoke(*args: str):
    return CliRunner().invoke(
        teamcity.main,
        args,
        env={"TEAMCITY_URL": "https://127.0.0.1:9989", "TEAMCITY_TOKEN": TOKEN},
    )


def test_transport_uses_generic_url_and_optional_host_override():
    client = MagicMock()
    client.__enter__.return_value.get.return_value = response()
    config = teamcity.Config(
        "https://127.0.0.1:9989", "ci.example.test", None, False, 30
    )
    with (
        patch.object(teamcity.httpx, "Client", return_value=client) as factory,
        patch.dict(os.environ, {"TEAMCITY_TOKEN": TOKEN}),
    ):
        assert json.loads(teamcity.request(config, "/app/rest/server").content) == {
            "count": 0
        }
    assert factory.call_args.kwargs["base_url"] == "https://127.0.0.1:9989"
    assert factory.call_args.kwargs["headers"]["Host"] == "ci.example.test"
    assert client.__enter__.return_value.get.call_args.kwargs["extensions"] == {
        "sni_hostname": "ci.example.test"
    }


def test_token_command_reads_first_line():
    config = teamcity.Config(
        "https://ci.example.test", None, "secret-tool token", True, 60
    )
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(
            teamcity.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, TOKEN + "\nnotes\n", ""),
        ) as run,
    ):
        assert teamcity.token(config) == TOKEN
    assert run.call_args.args[0] == ["secret-tool", "token"]


def test_next_href_is_preserved_and_unrelated_paths_are_rejected():
    href = "/app/rest/builds?locator=count:5,start:5&fields=count,nextHref"
    assert teamcity.rest_path(href) == href
    for path in (
        "https://other.example/app/rest/server",
        "/httpAuth/app/rest/server",
        "/app/rest/../login",
        "/app/rest/%2e%2e/login",
        "/app/rest/server#fragment",
        "/app/rest/server%0Aheader",
    ):
        with pytest.raises(Exception):
            teamcity.rest_path(path)


def test_build_branch_is_encoded_inside_locator():
    branch = "feature/test,status:SUCCESS"
    with patch.object(teamcity, "emit") as emit:
        result = invoke("builds", "--project", "Project", "--branch", branch)
    assert result.exit_code == 0
    locator = dict(emit.call_args.args[2])["locator"]
    assert "affectedProject:(id:Project)" in locator
    assert branch not in locator
    encoded = locator.split("$base64:")[1].split(")")[0]
    assert (
        base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode() == branch
    )


def test_queue_and_filtered_tests_use_their_supported_locators():
    with patch.object(teamcity, "emit") as emit:
        assert invoke("queue", "--project", "Project").exit_code == 0
    assert "project:(id:Project)" in dict(emit.call_args.args[2])["locator"]
    with patch.object(teamcity, "emit") as emit:
        assert invoke("tests", "123", "--limit", "5", "--start", "10").exit_code == 0
    assert emit.call_args.args[1] == "/app/rest/testOccurrences"
    locator = dict(emit.call_args.args[2])["locator"]
    for dimension in ("build:(id:123)", "status:FAILURE", "count:5", "start:10"):
        assert dimension in locator


def test_artifact_refuses_to_overwrite(tmp_path: Path):
    output = tmp_path / "artifact.bin"
    output.write_bytes(b"existing")
    with patch.object(teamcity, "request") as request:
        result = invoke("artifact", "123", "result.zip", "--output", str(output))
    assert result.exit_code == 1
    assert "already exists" in result.output
    request.assert_not_called()
    assert output.read_bytes() == b"existing"
