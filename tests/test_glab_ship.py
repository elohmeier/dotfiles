import json
import subprocess

import pytest
from click.testing import CliRunner

from scripts import glab_deploy, glab_ship


@pytest.mark.parametrize("failures", [0, 7, 31])
def test_create_mr_waits_for_source_branch(monkeypatch, capsys, failures):
    calls = []
    sleeps = []
    mr = {"iid": 71, "web_url": "https://gitlab.example/merge_requests/71"}

    def api(*args):
        calls.append(args)
        if len(calls) <= failures:
            raise subprocess.CalledProcessError(
                1,
                ["glab", "api"],
                output=json.dumps({"message": {"source_branch": ["does not exist"]}}),
                stderr="glab: source_branch does not exist",
            )
        return mr

    monkeypatch.setattr(glab_ship, "api", api)
    monkeypatch.setattr(glab_ship.time, "sleep", sleeps.append)

    if failures == 31:
        with pytest.raises(glab_ship.click.ClickException, match="rerun glab-ship"):
            glab_ship.create_mr("fixes", "main", "fixes", ["-F", "squash=false"])
    else:
        assert (
            glab_ship.create_mr("fixes", "main", "fixes", ["-F", "squash=false"]) == mr
        )

    assert len(calls) == min(failures + 1, 31)
    assert sleeps == [2] * min(failures, 30)
    assert all(call == calls[0] for call in calls)
    assert capsys.readouterr().err.count("retrying") == bool(failures)


@pytest.mark.parametrize(
    "output",
    [
        '{"message":{"title":["cannot be blank"]}}',
        '{"message":"403 Forbidden"}',
        '{"message":{"target_branch":["does not exist"]}}',
        "Bad Gateway",
        "",
    ],
)
def test_create_mr_does_not_retry_other_errors(monkeypatch, output):
    error = subprocess.CalledProcessError(1, ["glab", "api"], output=output)

    def api(*args):
        raise error

    monkeypatch.setattr(glab_ship, "api", api)
    monkeypatch.setattr(
        glab_ship.time, "sleep", lambda _: pytest.fail("unexpected retry")
    )
    with pytest.raises(subprocess.CalledProcessError) as exc:
        glab_ship.create_mr("fixes", "main", "fixes", [])
    assert exc.value is error


@pytest.mark.parametrize("cli, action", [(glab_ship, "ship"), (glab_deploy, "deploy")])
def test_cli_reports_api_error_without_traceback(monkeypatch, cli, action):
    def fail(*args):
        raise subprocess.CalledProcessError(
            1, ["glab", "api"], stderr="glab: 403 Forbidden"
        )

    monkeypatch.setattr(cli, action, fail)
    monkeypatch.setattr(cli.signal, "signal", lambda *args: None)
    result = CliRunner().invoke(cli.main)

    assert result.exit_code == 1
    assert "403 Forbidden" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("error", [glab_ship.click.ClickException, KeyboardInterrupt])
def test_merge_restores_approval_rules_when_creation_stops(monkeypatch, error):
    rules = {11289: 1}
    updates = []

    def create(*args):
        raise error("stopped")

    monkeypatch.setattr(glab_ship.subprocess, "check_call", lambda *args: None)
    monkeypatch.setattr(glab_ship, "approval_rules", lambda target: rules)
    monkeypatch.setattr(glab_ship, "set_rules", updates.append)
    monkeypatch.setattr(glab_ship, "create_mr", create)

    with pytest.raises(error):
        glab_ship.merge("fixes", "main", None, False, "fixes")

    assert updates == [{11289: 0}, rules]


@pytest.mark.parametrize("status", ["success", "failed", "canceled", "skipped"])
def test_wait_pipeline_follows_approval_through_rollout(monkeypatch, capsys, status):
    source = {
        "id": 1099492,
        "status": "running",
        "web_url": "https://gitlab.example/logstash-filter/-/pipelines/1099492",
    }
    downstream = {
        "id": 1099504,
        "project_id": 459,
        "ref": "309b8a11/obsp/349",
        "status": "running",
        "web_url": "https://gitlab.example/elastic-deploy/-/pipelines/1099504",
    }
    bridge = {
        "id": 3370212,
        "name": "deploy_obsp",
        "stage": "obsp",
        "status": "running",
        "downstream_pipeline": downstream,
    }
    gate = {"id": 3370260, "name": "wait_for_merge_request", "status": "manual"}
    mr = {
        "state": "opened",
        "description": "<!-- @@@1099504@@@349@@@309b8a11/obsp/349@@@elastic -->",
        "web_url": "https://gitlab.example/elastic-deploy/-/merge_requests/371",
    }
    responses = {
        "projects/:id/pipelines?sha=309b8a11&ref=main": [source],
        "projects/:id/pipelines/1099492": source,
        "projects/:id/pipelines/1099492/jobs?per_page=100": [],
        "projects/:id/pipelines/1099492/bridges?per_page=100": [bridge],
        "projects/459/pipelines/1099504": downstream,
        "projects/459/pipelines/1099504/jobs?per_page=100": [
            {"name": "create_merge_request", "status": "failed", "allow_failure": True},
            gate,
        ],
        "projects/459/pipelines/1099504/bridges?per_page=100": [],
        "projects/459/merge_requests?scope=all&source_branch=obsp-349-staging&target_branch=obsp-approved": [
            mr
        ],
    }
    states = [
        ("opened", "manual", "manual", "manual"),
        ("merged", "manual", "manual", "manual"),
        ("merged", "running", "running", "running"),
        ("merged", status, status, status),
    ]
    seen = []

    def api(path):
        if path == "projects/:id/pipelines/1099492":
            state = states[len(seen)]
            seen.append(state)
            mr["state"], gate["status"], downstream["status"], source["status"] = state
            bridge["status"] = downstream["status"]
        return responses[path]

    monkeypatch.setattr(glab_ship, "api", api)
    monkeypatch.setattr(glab_deploy, "api", api)
    monkeypatch.setattr(glab_deploy.time, "sleep", lambda _: None)

    if status == "success":
        glab_ship.wait_pipeline("309b8a11", "main")
    else:
        with pytest.raises(glab_ship.click.ClickException, match="main pipeline"):
            glab_ship.wait_pipeline("309b8a11", "main")

    assert seen == states
    output = capsys.readouterr().out
    assert mr["web_url"] in output
    assert "Deployment approval MR merged" in output
    assert ("main pipeline: success" in output) == (status == "success")


@pytest.mark.parametrize(
    "state", ["merged", "unmerged", "squashed", "pull-fails", "checkout-fails"]
)
def test_local_branch_cleanup(tmp_path, monkeypatch, state):
    remote = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    def git(*args):
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.PIPE
        ).strip()

    git("init", "-b", "main")
    for key, value in {
        "user.name": "Test",
        "user.email": "test@example.com",
        "commit.gpgsign": "false",
        "core.hooksPath": "/dev/null",
        "fetch.prune": "false",
    }.items():
        git("config", key, value)
    file = work / "file.txt"
    file.write_text("base\n")
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    git("remote", "add", "origin", str(remote))
    git("push", "-u", "origin", "main")
    git("checkout", "-b", "feature")
    file.write_text("feature\n")
    git("commit", "-am", "feature")
    head = git("rev-parse", "HEAD")
    git("push", "-u", "origin", "feature")
    git("checkout", "main")
    if state == "squashed":
        git("merge", "--squash", "feature")
        git("commit", "-m", "squash")
    elif state != "unmerged":
        git("merge", "--no-ff", "feature", "-m", "merge")
    merged = git("rev-parse", "HEAD")
    git("push", "origin", "main")
    git("checkout", "feature")
    if state == "pull-fails":
        git("remote", "set-url", "origin", str(tmp_path / "missing.git"))
    else:
        git("branch", "-f", "main", base)
    if state == "checkout-fails":
        file.write_text("uncommitted work\n")
    mr = {
        "iid": 1,
        "state": "merged",
        "sha": head,
        "merge_commit_sha": merged,
        "web_url": "https://example.com/mr/1",
    }
    responses = {
        "projects/:id": {"default_branch": "main"},
        "projects/:id/merge_requests?source_branch=feature": [mr],
        "projects/:id/releases": [],
    }
    monkeypatch.setattr(glab_ship, "api", lambda path: responses[path])
    monkeypatch.setattr(glab_ship, "wait_pipeline", lambda *args: None)
    monkeypatch.setattr(glab_ship, "show", lambda *args: None)

    glab_ship.ship(None)

    branches = git("for-each-ref", "--format=%(refname)", "refs/heads").splitlines()
    assert ("refs/heads/feature" in branches) == (state != "merged")
    assert git("branch", "--show-current") == (
        "feature" if state == "checkout-fails" else "main"
    )
    if state == "merged":
        assert git("rev-parse", "HEAD") == merged
    if state == "checkout-fails":
        assert file.read_text() == "uncommitted work\n"


@pytest.mark.parametrize(
    "mr, title, squash, parents",
    [
        (None, None, None, "a b"),
        (None, None, False, "a"),
        (None, "chore: merge upstream/main", False, "a b"),
        ({"iid": 7, "web_url": "u"}, None, None, "a b"),
        ({"iid": 7, "web_url": "u"}, "feat: x", False, "a b"),
    ],
)
def test_merge_title_and_squash(monkeypatch, mr, title, squash, parents):
    events = []

    def api(*args):
        events.append(("api", *args))
        return {"iid": 7, "web_url": "https://example.com/mr/7"}

    monkeypatch.setattr(glab_ship, "api", api)
    monkeypatch.setattr(
        glab_ship, "git", lambda *a: {"%P": parents, "%s": "subject"}[a[-1][9:]]
    )
    monkeypatch.setattr(
        glab_ship.subprocess, "check_call", lambda a: events.append(("push",))
    )
    monkeypatch.setattr(glab_ship, "approval_rules", lambda target: {})
    monkeypatch.setattr(glab_ship, "set_rules", lambda rules: None)
    monkeypatch.setattr(glab_ship, "show", lambda *a: None)
    monkeypatch.setattr(glab_ship, "poll", lambda fn: {"iid": 7})

    if not mr and not title and parents == "a b":
        with pytest.raises(glab_ship.click.ClickException):
            glab_ship.merge("update", "main", mr, squash, title)
        assert events == []
        return
    glab_ship.merge("update", "main", mr, squash, title)

    squash_args = [] if squash is None else ["-F", f"squash={str(squash).lower()}"]
    if mr:
        put = [("api", "projects/:id/merge_requests/7", "-X", "PUT", *squash_args)]
        put[0] += ("-f", f"title={title}") if title else ()
        assert events == [*(put if title or squash_args else []), ("push",)]
    else:
        create = events[1]
        assert events[0] == ("push",) and create[1:4] == (
            "projects/:id/merge_requests",
            "-X",
            "POST",
        )
        assert f"title={title or 'subject'}" in create
        assert all(a in create for a in squash_args)
