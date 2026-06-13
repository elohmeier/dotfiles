"""Clone all GitLab repositories using ghq."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable, Literal
from urllib.parse import urlsplit

import rich_click as click
from rich.console import Console
from rich.progress import Progress

console = Console()

Remote = Literal["ssh", "https"]
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


def _repo_url(repo: dict[str, Any], remote: Remote, clone_host: str) -> str:
    """Return the requested clone URL."""
    url = repo["http_url_to_repo" if remote == "https" else "ssh_url_to_repo"]
    if remote != "https":
        return url

    parts = urlsplit(url)
    return f"{parts.scheme}://{_host_netloc(clone_host)}{parts.path}"


def _api_url(repo: dict[str, Any], remote: Remote, host: str) -> str | None:
    """Return the HTTPS URL for the configured GitLab host."""
    if remote != "https":
        return None

    parts = urlsplit(repo["http_url_to_repo"])
    return f"{parts.scheme}://{_host_netloc(host)}{parts.path}"


def _clone_env(remote: Remote, host: str, clone_host: str) -> dict[str, str] | None:
    """Return env that maps clone_host URLs to host URLs for git."""
    if remote != "https" or _host_netloc(host) == _host_netloc(clone_host):
        return None

    return os.environ | {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.https://{_host_netloc(host)}/.insteadOf",
        "GIT_CONFIG_VALUE_0": f"https://{_host_netloc(clone_host)}/",
    }


def _set_origin_to_api_url(repo: dict[str, Any], remote: Remote, host: str) -> None:
    """Keep remotes usable after ghq placed the repo under clone_host."""
    api_url = _api_url(repo, remote, host)
    if not api_url:
        return

    ghq_result = subprocess.run(
        ["ghq", "list", "-p", "-e", repo["path_with_namespace"]],
        capture_output=True,
        text=True,
    )
    repo_path = ghq_result.stdout.strip().splitlines()
    if ghq_result.returncode == 0 and repo_path:
        subprocess.run(
            ["git", "-C", repo_path[0], "remote", "set-url", "origin", api_url],
            capture_output=True,
        )


def _clone_repo(
    repo: dict[str, Any],
    dry_run: bool,
    remote: Remote,
    host: str,
    clone_host: str,
) -> tuple[bool | str, str]:
    """Clone a single repository via ghq."""
    repo_url = _repo_url(repo, remote, clone_host)
    name = repo["path_with_namespace"]
    command = ["ghq", "get", "--update", repo_url]

    if dry_run:
        return f"Would run: {' '.join(command)}", name

    result = subprocess.run(
        command,
        capture_output=True,
        env=_clone_env(remote, host, clone_host),
        text=True,
    )
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or False, name
    _set_origin_to_api_url(repo, remote, host)
    return True, name


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without cloning",
)
@click.option(
    "--parallel",
    default=1,
    type=int,
    help="Number of parallel clone operations (default: 1)",
)
@click.option(
    "--remote",
    type=click.Choice(["ssh", "https"]),
    default="ssh",
    show_default=True,
    help="Clone URL type to pass to ghq",
)
@click.option(
    "--include-dummy-test",
    is_flag=True,
    help="Include repositories whose name/path looks like dummy or test data",
)
@click.option(
    "--host",
    envvar="GITLAB_HOST",
    default="gitlab-proxy.example.com",
    show_default=True,
    help="GitLab host for glab API calls and HTTPS git access",
)
@click.option(
    "--clone-host",
    default="gitlab.services.example.it",
    show_default=True,
    help="GitLab host to keep in ghq paths and HTTPS remotes",
)
def main(
    dry_run: bool,
    parallel: int,
    remote: Remote,
    include_dummy_test: bool,
    host: str,
    clone_host: str,
) -> None:
    """Clone all accessible GitLab repositories into ghq."""
    all_repos = _fetch_repositories(host)
    if not all_repos:
        console.print("[yellow]No repositories found[/yellow]")
        sys.exit(0)

    console.print(f"Found {len(all_repos)} repositories total")
    filtered_repos = _filter_group_repositories(all_repos, include_dummy_test)
    _ensure_ghq_is_available()

    with Progress() as progress:
        task = progress.add_task("Processing repos...", total=len(filtered_repos))

        if parallel == 1:
            for repo in filtered_repos:
                name = repo["path_with_namespace"]
                progress.update(task, description=f"Processing {name}")

                result, repo_name = _clone_repo(repo, dry_run, remote, host, clone_host)
                if dry_run:
                    console.print(f"[dim]{result}[/dim]")
                elif result is not True:
                    console.print(f"[red]Failed {repo_name}: {result}[/red]")

                progress.update(task, advance=1)
        else:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(
                        _clone_repo, repo, dry_run, remote, host, clone_host
                    ): repo
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
