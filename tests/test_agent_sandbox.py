"""Shared runner command and credential boundaries, without model API calls."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1] / "home/dot_config/pi-less-yolo"


@pytest.fixture
def runner(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    workspace = tmp_path / "project with spaces"
    workspace.mkdir()
    runtime = tmp_path / "runtime"
    runtime.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "if sys.argv[1] == 'run':\n"
        "    print(json.dumps(sys.argv[1:]))\n"
    )
    runtime.chmod(0o755)
    env = {
        k: v
        for k, v in os.environ.items()
        if k in ("PATH", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "TMPDIR")
    }
    env.update(
        HOME=str(home),
        PI_CONTAINER_RUNTIME=str(runtime),
        PI_EGRESS="",
        PI_NO_GITCONFIG="1",
        OPENAI_API_KEY="test-openai",
        ANTHROPIC_API_KEY="test-anthropic",
        CLAUDE_CODE_OAUTH_TOKEN="test-oauth",
    )

    def run(agent, *args):
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "exact_tasks/exact_agent" / f"executable_{agent}"),
                *args,
            ],
            env=env,
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    return run, env


@pytest.mark.parametrize("agent", ["pi", "codex", "claude"])
def test_agent_launch_mounts_and_arguments(runner, agent):
    run, env = runner
    args = run(agent, "--version")
    assert "--cap-drop=ALL" in args and "--security-opt=no-new-privileges" in args
    assert args[-1] == "--version"
    assert agent in args[args.index("pi-less-yolo:latest") + 1 :]
    assert not any("docker.sock" in arg for arg in args)
    if agent == "pi":
        assert f"{env['HOME']}/.pi/agent:/pi-agent" in args
    else:
        assert f"{env['HOME']}/.local/share/agent-sandbox/{agent}:/home/piuser" in args
        assert not any(":/pi-agent" in arg for arg in args)
        assert not any(f"{env['HOME']}/.{agent}:" in arg for arg in args)
    if agent == "codex":
        assert "--dangerously-bypass-approvals-and-sandbox" in args
        assert "OPENAI_API_KEY=test-openai" in args
        assert not any("test-anthropic" in arg or "test-oauth" in arg for arg in args)
        assert 'model_provider="sandbox-openai"' in args
    elif agent == "claude":
        assert "--dangerously-skip-permissions" not in args
        assert "ANTHROPIC_API_KEY=test-anthropic" in args
        assert not any("test-openai" in arg for arg in args)


def test_shell_uses_selected_agent_home(runner):
    run, env = runner
    env["AGENT"] = "codex"
    assert run("shell", "-c", "echo hello")[-3:] == ["bash", "-c", "echo hello"]


def test_codex_subscription_does_not_force_api_provider(runner):
    run, env = runner
    del env["OPENAI_API_KEY"]
    args = run("codex", "login", "--device-auth")
    assert not any("sandbox-openai" in arg for arg in args)
    assert args[-2:] == ["login", "--device-auth"]


def test_egress_default_rejects_host_network_bypass(runner):
    _, env = runner
    del env["PI_EGRESS"]
    env["PI_LOCAL_MODELS"] = "1"
    result = subprocess.run(
        ["bash", str(ROOT / "exact_tasks/exact_agent/executable_codex"), "--version"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "mutually exclusive" in result.stderr


@pytest.mark.parametrize(
    ("agent", "hosts"),
    [
        ("codex", {"api.openai.com", "auth.openai.com", "chatgpt.com"}),
        (
            "claude",
            {
                "api.anthropic.com",
                "console.anthropic.com",
                "platform.claude.com",
                "claude.ai",
            },
        ),
    ],
)
def test_provider_allowlist_uses_individual_hosts(tmp_path, agent, hosts):
    env = dict(os.environ, AGENT=agent, PI_EGRESS_DIR=str(tmp_path))
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1/egress.sh"; egress_write_config interactive',
            "test",
            str(ROOT),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    allowed = {
        line.removeprefix("allow=")
        for line in (tmp_path / "config").read_text().splitlines()
        if line.startswith("allow=")
    }
    assert allowed == hosts


@pytest.mark.skipif(
    not os.environ.get("PI_EGRESS_TEST_IMAGE"),
    reason="Set PI_EGRESS_TEST_IMAGE for Docker",
)
def test_live_agents_have_separate_proxies_and_scoped_credentials(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "mise.toml").write_text("[env]\n")
    state = tmp_path / "state"
    state.mkdir()
    (state / "secrets.rules").write_text("OPENAI_API_KEY hosts=api.openai.com\n")
    env = {
        k: v
        for k, v in os.environ.items()
        if k in ("PATH", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "TMPDIR")
    }
    env.update(
        HOME=str(tmp_path / "home"),
        DOCKER_CONFIG=os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker")),
        XDG_DATA_HOME=str(tmp_path / "data"),
        PI_EGRESS_GLOBAL_DIR=str(state),
        PI_PROXY_IMAGE=os.environ["PI_EGRESS_TEST_IMAGE"],
        PI_NO_GITCONFIG="1",
        OPENAI_API_KEY="test-real-provider-key",
        PI_EGRESS_BLOCK_DNS="1",
    )
    tasks = ROOT / "exact_tasks/exact_agent"
    contexts = []
    try:
        for agent, version in (
            ("pi", "0.85.1"),
            ("codex", "codex-cli"),
            ("claude", "Claude Code"),
        ):
            env["AGENT"] = agent
            result = subprocess.run(
                ["bash", str(tasks / f"executable_{agent}"), "--version"],
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=90,
            )
            assert result.returncode == 0, result.stderr
            assert version in result.stdout
            # Shells use exactly the same mount, environment, and network setup.
            result = subprocess.run(
                [
                    "bash",
                    str(tasks / "executable_shell"),
                    "-c",
                    'test -f "$CODEX_CA_CERTIFICATE" && '
                    'test "$OPENAI_API_KEY" != test-real-provider-key && '
                    "test ! -e /egress/secrets.env && "
                    "test ! -S /var/run/docker.sock && "
                    '! curl --noproxy "*" -fsS --max-time 2 http://1.1.1.1',
                ],
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
        contexts = list((state / "projects").iterdir())
        assert len(contexts) == 3
        assert len({(ctx / "web-port").read_text() for ctx in contexts}) == 3
        assert (
            len(
                {
                    (ctx / "mitmproxy/mitmproxy-ca-cert.pem").read_bytes()
                    for ctx in contexts
                }
            )
            == 3
        )
        assert (
            len({(ctx / "secrets.env").read_text().split("\t")[1] for ctx in contexts})
            == 3
        )
    finally:
        for agent in ("pi", "codex", "claude"):
            subprocess.run(
                ["bash", str(tasks / "executable_egress"), "stop"],
                cwd=workspace,
                env=dict(env, AGENT=agent),
                capture_output=True,
                timeout=30,
            )
