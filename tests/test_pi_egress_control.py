"""Host-side scope and approval-boundary regressions (no Docker required)."""

import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import time
import tomllib

from click.testing import CliRunner
import pytest

from scripts import pi_egress_control as control

TASKS = (
    Path(__file__).resolve().parents[1]
    / "home/dot_config/pi-less-yolo/exact_tasks/exact_pi"
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("PI_EGRESS_"):
            monkeypatch.delenv(key)
    root = tmp_path / "project with spaces"
    root.mkdir()
    (root / "mise.toml").write_text(
        '# keep this comment\n[env]\nUNCHANGED = "value"\nPI_EGRESS_ALLOW = "existing.test:443"\n'
    )
    monkeypatch.chdir(root)
    monkeypatch.setenv("PI_EGRESS_GLOBAL_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PI_EGRESS_ALLOW", "existing.test:443")
    ctx = control.Context.current()
    result = CliRunner().invoke(control.main, ["snapshot"])
    assert result.exit_code == 0, result.output
    return ctx


def invoke(*args):
    result = CliRunner().invoke(control.main, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_project_identity_subdirectory_and_worktrees(project, monkeypatch, tmp_path):
    assert project.root
    child = project.root / "src"
    child.mkdir()
    monkeypatch.chdir(child)
    assert control.Context.current() == project
    other = tmp_path / "other-worktree"
    other.mkdir()
    (other / ".git").write_text("gitdir: somewhere\n")
    monkeypatch.chdir(other)
    assert control.Context.current().state != project.state
    output = invoke("context")
    assert "PI_EGRESS_WEB_PORT=0" in output
    assert "PI_EGRESS_SUBNET=''" in output


def test_project_save_preserves_file_and_only_activates_delta(project):
    assert project.root
    target = project.root / "mise.toml"
    target.write_text(
        target.read_text().replace(
            "existing.test:443", "existing.test:443 agent-added.test:443"
        )
    )
    invoke("rule", "--scope", "project", "allow", "APPROVED.test:8443")
    assert target.read_text().startswith("# keep this comment")
    values = tomllib.loads(target.read_text())["env"]
    assert values["UNCHANGED"] == "value"
    assert "agent-added.test:443" in values["PI_EGRESS_ALLOW"]
    assert control.read_rules(project.state / "project.allow") == [
        "approved.test:8443",
        "existing.test:443",
    ]
    assert control.read_rules(project.global_dir / "rules.allow") == []
    invoke("rule", "--scope", "project", "allow", "approved.test:8443")
    assert (
        tomllib.loads(target.read_text())["env"]["PI_EGRESS_ALLOW"].count(
            "approved.test:8443"
        )
        == 1
    )


def test_global_changes_propagate_without_reloading_projects(
    project, monkeypatch, tmp_path
):
    other = tmp_path / "other"
    other.mkdir()
    (other / "mise.toml").write_text("[env]\n")
    monkeypatch.chdir(other)
    monkeypatch.setenv("PI_EGRESS_ALLOW", "other.test:443")
    invoke("snapshot")
    ctx2 = control.Context.current()
    invoke("rule", "--scope", "global", "deny", "existing.test:443")
    for ctx in (project, ctx2):
        assert control.read_rules(ctx.state / "rules.deny") == ["existing.test:443"]
    assert control.read_rules(project.state / "project.allow") == ["existing.test:443"]
    assert control.read_rules(ctx2.state / "project.allow") == ["other.test:443"]


def test_remove_only_affects_selected_scope(project):
    invoke("rule", "--scope", "global", "allow", "existing.test:443")
    invoke("rule", "--scope", "project", "--remove", "allow", "existing.test:443")
    assert not control.read_rules(project.state / "project.allow")
    assert control.read_rules(project.global_dir / "rules.allow") == [
        "existing.test:443"
    ]


def test_literal_policy_required_and_no_template_evaluation(project):
    assert project.root
    target = project.root / "mise.toml"
    target.write_text(
        "[env]\nPI_EGRESS_ALLOW = \"{{ exec(command='touch should-not-exist') }}\"\n"
    )
    result = CliRunner().invoke(
        control.main, ["rule", "--scope", "project", "allow", "safe.test:443"]
    )
    assert result.exit_code != 0 and "literal string" in result.output
    assert not (project.root / "should-not-exist").exists()
    assert control.read_rules(project.state / "project.allow") == ["existing.test:443"]


def test_broker_saves_only_live_request_to_bound_project(project, tmp_path):
    request_id = "0123456789abcdef"
    (project.state / "config").write_text("timeout=60\n")
    (project.state / "pending" / request_id).write_text("requested.test:443\n")
    # Proxy metadata and arbitrary payload paths must never select the destination.
    (project.state / "project").write_text(str(tmp_path / "wrong-project"))
    (project.state / "save" / request_id).write_text(
        json.dumps(
            dict(
                scope="project",
                kind="allow",
                path=str(tmp_path / "wrong.toml"),
                pattern="not-requested.test",
            )
        )
    )
    control.process_saves(project)
    assert control.read_rules(project.state / "project.allow") == [
        "existing.test:443",
        "requested.test:443",
    ]
    assert (project.state / "decisions" / request_id).read_text() == "allow"
    assert not (tmp_path / "wrong.toml").exists()


@pytest.mark.parametrize("answered", [False, True])
def test_broker_ignores_expired_or_answered_requests(project, answered):
    request_id = "0123456789abcdef"
    request = project.state / "pending" / request_id
    request.write_text("expired.test:443")
    (project.state / "config").write_text("timeout=1\n")
    if answered:
        (project.state / "decisions" / request_id).write_text("deny")
    else:
        os.utime(request, (time.time() - 10, time.time() - 10))
    (project.state / "save" / request_id).write_text(
        '{"scope":"project","kind":"allow"}'
    )
    control.process_saves(project)
    assert "expired.test:443" not in control.read_rules(project.state / "project.allow")
    assert not (project.state / "save" / request_id).exists()


def test_cli_scope_and_reload(project, monkeypatch):
    result = subprocess.run(
        [
            "bash",
            str(TASKS / "executable_egress"),
            "allow",
            "--scope",
            "project",
            "cli.test:443",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "project →" in result.stdout
    assert control.read_rules(project.state / "project.allow") == [
        "cli.test:443",
        "existing.test:443",
    ]
    monkeypatch.setenv("PI_EGRESS_ALLOW", "reloaded.test:443")
    invoke("snapshot")
    assert control.read_rules(project.state / "project.allow") == ["reloaded.test:443"]


def test_global_context_keeps_other_projects_out_of_proxy_mount(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_EGRESS_PROJECT_ROOT", "")
    monkeypatch.delenv("PI_EGRESS_DIR", raising=False)
    monkeypatch.setenv("PI_EGRESS_GLOBAL_DIR", str(tmp_path / "state"))
    ctx = control.Context.current()
    assert ctx.state == ctx.global_dir / "global"
    result = CliRunner().invoke(
        control.main, ["rule", "--scope", "project", "allow", "host.test"]
    )
    assert result.exit_code != 0


def test_watch_saves_exact_port_to_displayed_project(project):
    request_id = "0123456789abcdef"
    (project.state / "pending" / request_id).write_text("watch.test:8443\n")
    pid, terminal = pty.fork()
    if pid == 0:
        os.execvp(
            "bash",
            ["bash", str(TASKS / "executable_egress"), "watch", "--scope", "project"],
        )
    output = b""
    deadline = time.monotonic() + 10
    try:
        while b"choice [d]:" not in output and time.monotonic() < deadline:
            if select.select([terminal], [], [], 0.1)[0]:
                output += os.read(terminal, 4096)
        assert b"save project allow" in output
        assert project.root and str(project.root / "mise.toml").encode() in output
        os.write(terminal, b"A\n")
        decision = project.state / "decisions" / request_id
        while not decision.exists() and time.monotonic() < deadline:
            if select.select([terminal], [], [], 0.05)[0]:
                output += os.read(terminal, 4096)
        assert decision.exists(), output.decode()
        assert decision.read_text().strip() == "allow"
        assert control.read_rules(project.state / "project.allow") == [
            "existing.test:443",
            "watch.test:8443",
        ]
        assert not control.read_rules(project.global_dir / "rules.allow")
    finally:
        os.close(terminal)
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)


def test_project_save_rejects_symlink(project, tmp_path):
    assert project.root
    target = project.root / "mise.toml"
    target.unlink()
    outside = tmp_path / "outside.toml"
    outside.write_text('[env]\nSECRET="private"\n')
    target.symlink_to(outside)
    result = CliRunner().invoke(
        control.main, ["rule", "--scope", "project", "allow", "safe.test:443"]
    )
    assert result.exit_code != 0 and "symlinked" in result.output
    assert outside.read_text() == '[env]\nSECRET="private"\n'
    assert target.is_symlink()
