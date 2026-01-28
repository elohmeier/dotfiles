"""Clone all GitLab repositories using ghq."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

import rich_click as click
from rich.console import Console
from rich.progress import Progress

console = Console()


def _fetch_repositories() -> list[dict[str, Any]]:
    """Return all repositories visible to the current user."""
    console.print("Fetching repositories...")
    all_repos: list[dict[str, Any]] = []
    page = 1

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
) -> list[dict[str, Any]]:
    """Keep only group repositories (exclude personal namespaces)."""
    filtered = [
        repo for repo in repos if repo.get("namespace", {}).get("kind") != "user"
    ]

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


def _clone_repo(repo: dict[str, Any], dry_run: bool) -> tuple[bool | str, str]:
    """Clone a single repository via ghq."""
    ssh_url = repo["ssh_url_to_repo"]
    name = repo["path_with_namespace"]
    command = ["ghq", "get", "--update", ssh_url]

    if dry_run:
        return f"Would run: {' '.join(command)}", name

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, name


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
def main(dry_run: bool, parallel: int) -> None:
    """Clone all accessible GitLab repositories into ghq."""
    all_repos = _fetch_repositories()
    if not all_repos:
        console.print("[yellow]No repositories found[/yellow]")
        sys.exit(0)

    console.print(f"Found {len(all_repos)} repositories total")
    filtered_repos = _filter_group_repositories(all_repos)
    _ensure_ghq_is_available()

    with Progress() as progress:
        task = progress.add_task("Processing repos...", total=len(filtered_repos))

        if parallel == 1:
            for repo in filtered_repos:
                ssh_url = repo["ssh_url_to_repo"]
                name = repo["path_with_namespace"]
                command = ["ghq", "get", "--update", ssh_url]

                progress.update(task, description=f"Processing {name}")

                if dry_run:
                    console.print(f"[dim]Would run: {' '.join(command)}[/dim]")
                else:
                    subprocess.run(
                        command,
                        capture_output=True,
                    )

                progress.update(task, advance=1)
        else:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(_clone_repo, repo, dry_run): repo
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
                    except Exception as exc:  # noqa: BLE001
                        console.print(f"[red]Error processing {name}: {exc}[/red]")

                    progress.update(task, advance=1)

    console.print("[green]Done![/green]")


__all__ = ["main"]
