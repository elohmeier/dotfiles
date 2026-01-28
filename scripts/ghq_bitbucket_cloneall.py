"""Clone all Bitbucket Server repositories using ghq."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
import rich_click as click
from rich.console import Console
from rich.progress import Progress

console = Console()


def _get_ssh_url(repo: dict[str, Any]) -> str | None:
    """Extract SSH clone URL from repo links."""
    for link in repo.get("links", {}).get("clone", []):
        if link.get("name") == "ssh":
            return link.get("href")
    return None


def _fetch_paginated(
    session: requests.Session, url: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Fetch all pages from a paginated Bitbucket API endpoint."""
    items: list[dict[str, Any]] = []
    params = params or {}
    params.setdefault("limit", 100)
    start = 0

    while True:
        params["start"] = start
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get("values", []))

        if data.get("isLastPage", True):
            break
        start = data.get("nextPageStart", start + params["limit"])

    return items


def _fetch_all_repos(base_url: str, session: requests.Session) -> list[dict[str, Any]]:
    """Fetch all repositories from all projects."""
    console.print("Fetching projects...")
    projects = _fetch_paginated(session, f"{base_url}/rest/api/1.0/projects")
    console.print(f"Found {len(projects)} projects")

    all_repos: list[dict[str, Any]] = []
    for project in projects:
        key = project["key"]
        repos = _fetch_paginated(
            session, f"{base_url}/rest/api/1.0/projects/{key}/repos"
        )
        console.print(f"  {key}: {len(repos)} repositories")
        all_repos.extend(repos)

    return all_repos


def _clone_repo(repo: dict[str, Any], dry_run: bool) -> tuple[bool | str, str]:
    """Clone a single repository via ghq."""
    ssh_url = _get_ssh_url(repo)
    name = f"{repo['project']['key']}/{repo['slug']}"

    if not ssh_url:
        return False, name

    command = ["ghq", "get", "--update", ssh_url]

    if dry_run:
        return f"Would run: {' '.join(command)}", name

    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0, name


@click.command()
@click.option(
    "--url",
    envvar="BITBUCKET_URL",
    required=True,
    help="Bitbucket Server base URL (or set BITBUCKET_URL)",
)
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
def main(url: str, dry_run: bool, parallel: int) -> None:
    """Clone all Bitbucket Server repositories into ghq."""
    username = os.environ.get("BITBUCKET_USERNAME")
    token = os.environ.get("BITBUCKET_TOKEN")

    if not username or not token:
        console.print("[red]BITBUCKET_USERNAME and BITBUCKET_TOKEN required[/red]")
        sys.exit(1)

    session = requests.Session()
    session.auth = (username, token)

    base_url = url.rstrip("/")
    all_repos = _fetch_all_repos(base_url, session)

    if not all_repos:
        console.print("[yellow]No repositories found[/yellow]")
        sys.exit(0)

    console.print(f"Found {len(all_repos)} repositories total")

    with Progress() as progress:
        task = progress.add_task("Processing repos...", total=len(all_repos))

        if parallel == 1:
            for repo in all_repos:
                ssh_url = _get_ssh_url(repo)
                name = f"{repo['project']['key']}/{repo['slug']}"
                progress.update(task, description=f"Processing {name}")

                if not ssh_url:
                    console.print(f"[yellow]No SSH URL for {name}[/yellow]")
                elif dry_run:
                    console.print(f"[dim]Would run: ghq get --update {ssh_url}[/dim]")
                else:
                    subprocess.run(
                        ["ghq", "get", "--update", ssh_url], capture_output=True
                    )

                progress.update(task, advance=1)
        else:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(_clone_repo, repo, dry_run): repo
                    for repo in all_repos
                }

                for future in as_completed(futures):
                    repo = futures[future]
                    name = f"{repo['project']['key']}/{repo['slug']}"

                    try:
                        result, repo_name = future.result()
                        progress.update(task, description=f"Processed {repo_name}")
                        if dry_run and isinstance(result, str):
                            console.print(f"[dim]{result}[/dim]")
                    except Exception as exc:  # noqa: BLE001
                        console.print(f"[red]Error processing {name}: {exc}[/red]")

                    progress.update(task, advance=1)

    console.print("[green]Done![/green]")


__all__ = ["main"]
