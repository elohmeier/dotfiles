"""Clone all GitLab repositories using ghq."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable
from urllib.parse import urlsplit

import rich_click as click
from rich.console import Console
from rich.progress import Progress

console = Console()

SKIP_RE = re.compile(
    r"(^|[-_/])([a-z0-9]*dummy[a-z0-9]*|[a-z0-9]*test[a-z0-9]*|deletion[-_]scheduled)([-_/]|$)",
    re.I,
)


def _fetch_repositories(host: str) -> list[dict[str, Any]]:
    """Return all repositories visible to the current user."""
    console.print("Fetching repositories...")
    all_repos: list[dict[str, Any]] = []
    page = 1
    env = os.environ | {"GITLAB_HOST": host}

    while True:
        result = subprocess.run(
            [
                "glab",
                "repo",
                "list",
                "-a",
                "-F",
                "json",
                "--per-page",
                "100",
                "--page",
                str(page),
            ],
            capture_output=True,
            env=env,
            text=True,
        )

        if result.returncode != 0:
            console.print(f"[red]Failed to fetch repos: {result.stderr}[/red]")
            sys.exit(1)

        repos = json.loads(result.stdout) if result.stdout else []
        if not repos:
            break

        all_repos.extend(repos)
        console.print(f"Fetched page {page} ({len(repos)} repositories)")
        page += 1

    return all_repos


def _filter_group_repositories(
    repos: Iterable[dict[str, Any]],
    include_dummy_test: bool,
) -> list[dict[str, Any]]:
    """Keep group repositories and skip dummy/test repos by default."""
    filtered = [
        repo for repo in repos if repo.get("namespace", {}).get("kind") != "user"
    ]

    if not include_dummy_test:
        before = len(filtered)
        filtered = [
            repo
            for repo in filtered
            if not SKIP_RE.search(
                " ".join(
                    [
                        repo.get("name", ""),
                        repo.get("path", ""),
                        repo.get("path_with_namespace", ""),
                    ]
                )
            )
        ]
        console.print(f"Skipped {before - len(filtered)} dummy/test repositories")

    if not filtered:
        console.print("[yellow]No group repositories found after filtering[/yellow]")
        sys.exit(0)

    console.print(f"Filtering down to {len(filtered)} group repositories")
    return filtered


def _ensure_ghq_is_available() -> None:
    """Exit with a helpful error if ghq is missing."""
    ghq_available = (
        subprocess.run(
            ["which", "ghq"],
            capture_output=True,
        ).returncode
        == 0
    )

    if not ghq_available:
        console.print("[yellow]ghq not found[/yellow]")
        sys.exit(1)


def _host_netloc(host: str) -> str:
    """Return host:port without scheme."""
    return urlsplit(host if "://" in host else f"https://{host}").netloc


def _repo_url(repo: dict[str, Any], host: str) -> str:
    """Return the HTTPS clone URL for host."""
    path = urlsplit(repo["http_url_to_repo"]).path
    return f"https://{_host_netloc(host)}{path}"


def _repo_path(repo: dict[str, Any], clone_host: str, ghq_root: str) -> str | None:
    """Return the existing ghq path for clone_host."""
    path = os.path.join(
        ghq_root,
        _host_netloc(clone_host),
        repo["path_with_namespace"],
    )
    return path if os.path.exists(os.path.join(path, ".git")) else None


def _api_url(repo: dict[str, Any], host: str) -> str:
    """Return the HTTPS URL for the configured GitLab host."""
    return _repo_url(repo, host)


def _clone_env(host: str, clone_host: str) -> dict[str, str] | None:
    """Return env that maps clone_host URLs to host URLs for git."""
    if _host_netloc(host) == _host_netloc(clone_host):
        return None

    return os.environ | {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.https://{_host_netloc(host)}/.insteadOf",
        "GIT_CONFIG_VALUE_0": f"https://{_host_netloc(clone_host)}/",
    }


def _set_origin_to_api_url(
    repo_path: str, repo: dict[str, Any], host: str
) -> bool | str:
    """Keep origin usable after ghq placed the repo under clone_host."""
    result = subprocess.run(
        [
            "git",
            "-C",
            repo_path,
            "remote",
            "set-url",
            "origin",
            _api_url(repo, host),
        ],
        capture_output=True,
        text=True,
    )
    return (
        True
        if result.returncode == 0
        else result.stderr.strip() or result.stdout.strip() or False
    )


def _sync_repo(
    repo: dict[str, Any],
    dry_run: bool,
    host: str,
    ghq_root: str,
) -> tuple[bool | str, str]:
    """Clone a repository or fetch its remote branches without pulling."""
    name = repo["path_with_namespace"]
    clone_host = _host_netloc(repo["http_url_to_repo"])
    repo_path = _repo_path(repo, clone_host, ghq_root)
    command = (
        [
            "git",
            "-C",
            repo_path,
            "fetch",
            "--prune",
            "--no-tags",
            "--no-prune-tags",
            "--no-recurse-submodules",
            _api_url(repo, host),
            "+refs/heads/*:refs/remotes/origin/*",
        ]
        if repo_path
        else ["ghq", "get", "--no-recursive", _repo_url(repo, clone_host)]
    )

    if dry_run:
        return f"Would run: {' '.join(command)}", name

    result = subprocess.run(
        command,
        capture_output=True,
        env=None if repo_path else _clone_env(host, clone_host),
        text=True,
    )
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or False, name
    repo_path = repo_path or _repo_path(repo, clone_host, ghq_root)
    return (
        _set_origin_to_api_url(repo_path, repo, host)
        if repo_path
        else "ghq did not create the expected checkout",
        name,
    )


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done",
)
@click.option(
    "--parallel",
    default=1,
    type=int,
    help="Number of parallel repository operations (default: 1)",
)
@click.option(
    "--include-dummy-test",
    is_flag=True,
    help="Include repositories whose name/path looks like dummy or test data",
)
@click.option(
    "--host",
    envvar="GITLAB_HOST",
    required=True,
    help="GitLab host for glab API calls and HTTPS git access",
)
def main(
    dry_run: bool,
    parallel: int,
    include_dummy_test: bool,
    host: str,
) -> None:
    """Clone or fetch all accessible GitLab repositories in ghq."""
    all_repos = _fetch_repositories(host)
    if not all_repos:
        console.print("[yellow]No repositories found[/yellow]")
        sys.exit(0)

    console.print(f"Found {len(all_repos)} repositories total")
    filtered_repos = _filter_group_repositories(all_repos, include_dummy_test)
    _ensure_ghq_is_available()
    ghq_root = subprocess.check_output(["ghq", "root"], text=True).strip()

    with Progress() as progress:
        task = progress.add_task("Processing repos...", total=len(filtered_repos))

        if parallel == 1:
            for repo in filtered_repos:
                name = repo["path_with_namespace"]
                progress.update(task, description=f"Processing {name}")

                result, repo_name = _sync_repo(repo, dry_run, host, ghq_root)
                if dry_run:
                    console.print(f"[dim]{result}[/dim]")
                elif result is not True:
                    console.print(f"[red]Failed {repo_name}: {result}[/red]")

                progress.update(task, advance=1)
        else:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(_sync_repo, repo, dry_run, host, ghq_root): repo
                    for repo in filtered_repos
                }

                for future in as_completed(futures):
                    repo = futures[future]
                    name = repo["path_with_namespace"]

                    try:
                        result, repo_name = future.result()
                        progress.update(task, description=f"Processed {repo_name}")
                        if dry_run:
                            console.print(f"[dim]{result}[/dim]")
                        elif result is not True:
                            console.print(f"[red]Failed {repo_name}: {result}[/red]")
                    except Exception as exc:  # noqa: BLE001
                        console.print(f"[red]Error processing {name}: {exc}[/red]")

                    progress.update(task, advance=1)

    console.print("[green]Done![/green]")


__all__ = ["main"]
