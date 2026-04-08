import subprocess

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def run(cmd: str) -> str:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True
    ).stdout.strip()


def parse_count_lines(raw: str) -> list[tuple[int, str]]:
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        count, rest = line.split(None, 1)
        results.append((int(count), rest))
    return results


def churn(since: str, limit: int):
    raw = run(
        f'git log --format=format: --name-only --since="{since}" | sed "/^$/d" | sort | uniq -c | sort -nr | head -{limit}'
    )
    if not raw:
        return
    table = Table(title="High-Churn Files", show_header=True)
    table.add_column("Changes", justify="right", style="bold")
    table.add_column("File")
    for count, path in parse_count_lines(raw):
        table.add_row(str(count), path)
    console.print(table)


def contributors():
    raw = run("git shortlog -sn --no-merges")
    if not raw:
        return
    table = Table(title="Contributors (by commits)", show_header=True)
    table.add_column("Commits", justify="right", style="bold")
    table.add_column("Author")
    for count, name in parse_count_lines(raw):
        table.add_row(str(count), name)
    console.print(table)


def bug_hotspots(since: str, limit: int):
    raw = run(
        f'git log -i -E --grep="\\b(fix|fixed|fixes|bug|broken)\\b" --name-only --format=\'\' --since="{since}" | sed "/^$/d" | sort | uniq -c | sort -nr | head -{limit}'
    )
    if not raw:
        return
    table = Table(title="Bug Hotspots", show_header=True)
    table.add_column("Bug Commits", justify="right", style="bold")
    table.add_column("File")
    for count, path in parse_count_lines(raw):
        table.add_row(str(count), path)
    console.print(table)


def velocity():
    raw = run("git log --format='%ad' --date=format:'%Y-%m' | sort | uniq -c")
    if not raw:
        return
    entries = parse_count_lines(raw)
    max_count = max(c for c, _ in entries)
    bar_width = 40
    table = Table(title="Commit Velocity", show_header=True)
    table.add_column("Month")
    table.add_column("Commits", justify="right", style="bold")
    table.add_column("")
    for count, month in entries:
        bar_len = round(count / max_count * bar_width)
        table.add_row(month, str(count), "█" * bar_len)
    console.print(table)


def firefighting(since: str):
    raw = run(
        f'git log --oneline --since="{since}" | grep -iE "revert|hotfix|emergency|rollback"'
    )
    if not raw:
        console.print(Panel("[green]No reverts/hotfixes found", title="Firefighting"))
        return
    table = Table(title="Firefighting (reverts/hotfixes)", show_header=True)
    table.add_column("Commit")
    for line in raw.splitlines():
        table.add_row(line.strip())
    console.print(table)


def branches(since: str, limit: int):
    raw = run(
        f'git for-each-ref --sort=-committerdate --format="%(committerdate:short) %(refname:short) %(authorname)" refs/heads/ | head -{limit}'
    )
    if not raw:
        return
    table = Table(title="Recent Branches", show_header=True)
    table.add_column("Last Commit")
    table.add_column("Branch")
    table.add_column("Author")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        date = parts[0] if len(parts) > 0 else ""
        branch = parts[1] if len(parts) > 1 else ""
        author = parts[2] if len(parts) > 2 else ""
        table.add_row(date, branch, author)
    console.print(table)


@click.command()
@click.option("--since", default="1 year ago", help="How far back to look.")
@click.option("--limit", default=20, help="Number of top entries to show.")
@click.option(
    "--section",
    type=click.Choice(
        [
            "all",
            "churn",
            "contributors",
            "bugs",
            "velocity",
            "firefighting",
            "branches",
        ]
    ),
    default="all",
    help="Which section to show.",
)
def main(since: str, limit: int, section: str):
    """Survey a git repo: churn, contributors, bug hotspots, velocity, firefighting, and branches."""
    run("git rev-parse --git-dir")  # fail fast if not a repo

    sections = {
        "churn": lambda: churn(since, limit),
        "contributors": contributors,
        "bugs": lambda: bug_hotspots(since, limit),
        "velocity": velocity,
        "firefighting": lambda: firefighting(since),
        "branches": lambda: branches(since, limit),
    }

    to_run = sections if section == "all" else {section: sections[section]}
    for i, fn in enumerate(to_run.values()):
        if i > 0:
            console.print()
        fn()
