import subprocess

import pytest

from scripts import glab_ship


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
