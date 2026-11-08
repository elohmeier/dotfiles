import io
import json
import os
import subprocess
import sys
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest
from click.testing import CliRunner

from scripts import h


@pytest.fixture
def repos(tmp_path, monkeypatch):
    root = tmp_path / "repos"
    root.mkdir()
    monkeypatch.setattr(h, "CODE_ROOT", root)
    return root


@pytest.fixture
def outputs(monkeypatch):
    values = {}
    monkeypatch.setattr(h, "output", lambda *args: values.get(args, ""))
    return values


def test_search_prefers_deepest_match_and_limits_depth(repos, outputs):
    for name in (
        "project",
        "host/project",
        "host/owner/Project",
        "host/owner/repo/project",
    ):
        (repos / name).mkdir(parents=True, exist_ok=True)
    for term in ("project", "Project"):
        result = CliRunner().invoke(h.main, [term])
        assert result.exit_code == 0, result.output
        assert result.stdout == f"{repos}/host/owner/Project\n"
    result = CliRunner().invoke(h.main, ["PROJECT"])
    assert result.exit_code == 1
    assert result.stdout == f"{Path.cwd()}\n"
    assert result.stderr == "PROJECT not found\n"


def test_search_breaks_ties_alphabetically(repos, outputs):
    for host in ("z.example", "a.example"):
        (repos / host / "owner/project").mkdir(parents=True)
    result = CliRunner().invoke(h.main, ["project"])
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{repos}/a.example/owner/project\n"


@pytest.mark.parametrize(
    "url",
    [
        "https://GitHub.COM/Owner/Repo.git",
        "ssh://git@GitHub.COM/Owner/Repo.git",
        "git@github.com:Owner/Repo.git",
        "gitea@github.com:Owner/Repo.git",
    ],
)
def test_existing_checkout_does_not_clone(repos, outputs, monkeypatch, url):
    path = repos / "github.com/Owner/Repo"
    path.mkdir(parents=True)

    def unexpected(*args, **kwargs):
        pytest.fail("existing checkouts must not run git clone")

    monkeypatch.setattr(h.subprocess, "run", unexpected)
    result = CliRunner().invoke(h.main, [url])
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{path}\n"


@pytest.mark.parametrize("private", [False, True])
def test_github_shorthand_uses_canonical_names_when_available(
    repos, outputs, monkeypatch, private
):
    path = repos / ("github.com/owner/repo" if private else "github.com/Owner/Repo")

    def urlopen(url):
        assert url == "https://api.github.com/repos/owner/repo"
        if private:
            raise HTTPError(url, 404, "Not Found", Message(), None)
        return io.StringIO(json.dumps({"owner": {"login": "Owner"}, "name": "Repo"}))

    def run(args, **kwargs):
        repo = "owner/repo" if private else "Owner/Repo"
        assert args == [
            "git",
            "clone",
            "--recursive",
            "--",
            f"git@github.com:{repo}.git",
            str(path),
        ]
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(h, "urlopen", urlopen)
    monkeypatch.setattr(h.subprocess, "run", run)
    result = CliRunner().invoke(h.main, ["owner/repo"])
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{path}\n"


def test_git_config_rewrites_run_in_order_with_backreferences(repos, outputs):
    outputs["git", "config", "--get-all", "h.rewrite"] = (
        r"^work:(.*)$ team/\1" "\n" r"^team/(.*)$ git@git.example:group/\1.git"
    )
    path = repos / "git.example/group/project"
    path.mkdir(parents=True)
    result = CliRunner().invoke(h.main, ["work:project"])
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{path}\n"


@pytest.mark.parametrize(
    "options", [[], ["--depth", "1", "--branch", "topic"], ["--help"]]
)
def test_clone_forwards_options_and_keeps_progress_off_stdout(
    repos, outputs, monkeypatch, options
):
    url = "https://git.example/group/subgroup/project.git"
    path = repos / "git.example/group/subgroup/project"

    def run(args, **kwargs):
        assert args == [
            "git",
            "clone",
            *(options or ["--recursive"]),
            "--",
            url,
            str(path),
        ]
        assert path.parent.is_dir()
        assert kwargs["stdout"] is sys.stderr
        print("Cloning...", file=kwargs["stdout"])
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(h.subprocess, "run", run)
    result = CliRunner().invoke(h.main, [url, *options])
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{path}\n"
    assert result.stderr == "Cloning...\n"


def test_failed_clone_preserves_exit_status_and_removes_created_parents(
    repos, outputs, monkeypatch
):
    host = repos / "git.example"
    host.mkdir()
    monkeypatch.setattr(
        h.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 23),
    )
    result = CliRunner().invoke(h.main, ["git@git.example:group/subgroup/project.git"])
    assert result.exit_code == 23
    assert result.stdout == ""
    assert host.is_dir()
    assert list(host.iterdir()) == []


@pytest.mark.parametrize("options", [[], ["-r", "100:HEAD"]])
def test_svn_uses_fetch_url_and_rewrites_repository_root(
    repos, outputs, monkeypatch, options
):
    term = "svn://alias/project/trunk"
    fetch = "https://svn.example/project/trunk"
    outputs["git", "config", "--get-all", "h.svn"] = "svn://alias/"
    outputs["git", "ls-remote", "--get-url", term] = fetch
    outputs[
        "svn", "info", "--non-interactive", "--show-item", "repos-root-url", fetch
    ] = "https://svn.example/project"
    path = repos / "alias/project"

    def run(args, **kwargs):
        assert args == [
            "git",
            "svn",
            "clone",
            "--rewrite-root=svn://alias/project",
            *(options or ["-r", "HEAD"]),
            "--",
            "https://svn.example/project",
            str(path),
        ]
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(h.subprocess, "run", run)
    result = CliRunner().invoke(h.main, [term, *options])
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{path}\n"


@pytest.mark.parametrize(
    "args", [[], ["-h"], ["--help"], ["missing"], ["unknown:pattern"]]
)
def test_errors_and_usage_print_current_directory(repos, outputs, args):
    result = CliRunner().invoke(h.main, args)
    assert result.exit_code == 1
    assert result.stdout == f"{Path.cwd()}\n"
    assert result.stderr


def test_real_git_clone_prints_only_destination(tmp_path):
    source = tmp_path / "source.git"
    subprocess.run(
        ["git", "init", "--bare", str(source)], capture_output=True, check=True
    )
    result = subprocess.run(
        [sys.executable, "-m", "scripts.h", source.as_uri()],
        env=os.environ
        | {
            "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        },
        capture_output=True,
        text=True,
    )
    destination = tmp_path / "repos" / source.relative_to(source.anchor).with_suffix("")
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{destination}\n"
    assert "Cloning into" in result.stderr
    assert (destination / ".git").is_dir()
