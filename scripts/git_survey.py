import subprocess
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def run(cmd: str, cwd: str | None = None) -> str:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    ).stdout.strip()


def find_repos(root: str) -> list[str]:
    return sorted(str(p.parent) for p in Path(root).rglob(".git") if p.is_dir())


def parse_count_lines(raw: str) -> list[tuple[int, str]]:
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        count, rest = line.split(None, 1)
        results.append((int(count), rest))
    return results


def collect_churn(
    since: str, limit: int, cwd: str | None = None
) -> list[tuple[int, str]]:
    raw = run(
        f'git log --format=format: --name-only --since="{since}" | sed "/^$/d" | sort | uniq -c | sort -nr | head -{limit}',
        cwd,
    )
    return parse_count_lines(raw)


def collect_contributors(cwd: str | None = None) -> list[tuple[int, str]]:
    return parse_count_lines(run("git shortlog -sn --no-merges", cwd))


def collect_bugs(
    since: str, limit: int, cwd: str | None = None
) -> list[tuple[int, str]]:
    raw = run(
        f'git log -i -E --grep="\\b(fix|fixed|fixes|bug|broken)\\b" --name-only --format=\'\' --since="{since}" | sed "/^$/d" | sort | uniq -c | sort -nr | head -{limit}',
        cwd,
    )
    return parse_count_lines(raw)


def collect_velocity(cwd: str | None = None) -> list[tuple[int, str]]:
    return parse_count_lines(
        run("git log --format='%ad' --date=format:'%Y-%m' | sort | uniq -c", cwd)
    )


def collect_firefighting(since: str, cwd: str | None = None) -> list[tuple[str, str]]:
    raw = run(
        f'git log --format="%an\t%s" --since="{since}"',
        cwd,
    )
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if not any(
            w in line.lower() for w in ("revert", "hotfix", "emergency", "rollback")
        ):
            continue
        author, _, subject = line.partition("\t")
        results.append((author, subject))
    return results


def collect_branches(
    since: str, limit: int, cwd: str | None = None
) -> list[tuple[str, str, str]]:
    raw = run(
        f'git for-each-ref --sort=-committerdate --format="%(committerdate:short) %(refname:short) %(authorname)" refs/heads/ | head -{limit}',
        cwd,
    )
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        results.append(
            (
                parts[0] if len(parts) > 0 else "",
                parts[1] if len(parts) > 1 else "",
                parts[2] if len(parts) > 2 else "",
            )
        )
    return results


def render_count_table(
    title: str, col: str, rows: list[tuple[str, int, str]], repo_col: bool = False
):
    if not rows:
        return
    table = Table(title=title, show_header=True)
    if repo_col:
        table.add_column("Repo", style="dim")
    table.add_column(col, justify="right", style="bold")
    table.add_column("" if col == "Commits" else "File")
    for repo, count, name in rows:
        args = [repo, str(count), name] if repo_col else [str(count), name]
        table.add_row(*args)
    console.print(table)


def render_velocity(rows: list[tuple[str, int, str]], repo_col: bool = False):
    if not rows:
        return
    max_count = max(c for _, c, _ in rows)
    bar_width = 40
    table = Table(title="Commit Velocity", show_header=True)
    if repo_col:
        table.add_column("Repo", style="dim")
    table.add_column("Month")
    table.add_column("Commits", justify="right", style="bold")
    table.add_column("")
    for repo, count, month in rows:
        bar_len = round(count / max_count * bar_width)
        args = (
            [repo, month, str(count), "█" * bar_len]
            if repo_col
            else [month, str(count), "█" * bar_len]
        )
        table.add_row(*args)
    console.print(table)


def render_firefighting(rows: list[tuple[str, str, str]], repo_col: bool = False):
    if not rows:
        console.print(Panel("[green]No reverts/hotfixes found", title="Firefighting"))
        return
    table = Table(title="Firefighting (reverts/hotfixes)", show_header=True)
    if repo_col:
        table.add_column("Repo", style="dim")
    table.add_column("Author")
    table.add_column("Commit")
    for repo, author, subject in rows:
        args = [repo, author, subject] if repo_col else [author, subject]
        table.add_row(*args)
    console.print(table)


def render_branches(rows: list[tuple[str, str, str, str]], repo_col: bool = False):
    if not rows:
        return
    table = Table(title="Recent Branches", show_header=True)
    if repo_col:
        table.add_column("Repo", style="dim")
    table.add_column("Last Commit")
    table.add_column("Branch")
    table.add_column("Author")
    for repo, date, branch, author in rows:
        args = [repo, date, branch, author] if repo_col else [date, branch, author]
        table.add_row(*args)
    console.print(table)


def _run_single(since: str, limit: int, section: str):
    sections = {
        "churn": lambda: render_count_table(
            "High-Churn Files",
            "Changes",
            [("", c, p) for c, p in collect_churn(since, limit)],
        ),
        "contributors": lambda: render_count_table(
            "Contributors (by commits)",
            "Commits",
            [("", c, n) for c, n in collect_contributors()],
        ),
        "bugs": lambda: render_count_table(
            "Bug Hotspots",
            "Bug Commits",
            [("", c, p) for c, p in collect_bugs(since, limit)],
        ),
        "velocity": lambda: render_velocity(
            [("", c, m) for c, m in collect_velocity()],
        ),
        "firefighting": lambda: render_firefighting(
            [("", a, s) for a, s in collect_firefighting(since)],
        ),
        "branches": lambda: render_branches(
            [("", d, b, a) for d, b, a in collect_branches(since, limit)],
        ),
    }
    to_run = sections if section == "all" else {section: sections[section]}
    for i, fn in enumerate(to_run.values()):
        if i > 0:
            console.print()
        fn()


def _run_scan(since: str, limit: int, section: str, repos: list[str], root: Path):
    def label(repo: str) -> str:
        return str(Path(repo).relative_to(root))

    def by_count(rows: list) -> list:
        return sorted(rows, key=lambda r: r[1], reverse=True)

    collectors = {
        "churn": lambda: by_count(
            [(label(r), c, p) for r in repos for c, p in collect_churn(since, limit, r)]
        ),
        "contributors": lambda: by_count(
            [(label(r), c, n) for r in repos for c, n in collect_contributors(r)]
        ),
        "bugs": lambda: by_count(
            [(label(r), c, p) for r in repos for c, p in collect_bugs(since, limit, r)]
        ),
        "velocity": lambda: sorted(
            [(label(r), c, m) for r in repos for c, m in collect_velocity(r)],
            key=lambda r: (r[2], r[0]),
        ),
        "firefighting": lambda: [
            (label(r), a, s) for r in repos for a, s in collect_firefighting(since, r)
        ],
        "branches": lambda: sorted(
            [
                (label(r), d, b, a)
                for r in repos
                for d, b, a in collect_branches(since, limit, r)
            ],
            key=lambda r: r[1],
            reverse=True,
        ),
    }
    renderers = {
        "churn": lambda rows: render_count_table(
            "High-Churn Files", "Changes", rows, repo_col=True
        ),
        "contributors": lambda rows: render_count_table(
            "Contributors (by commits)", "Commits", rows, repo_col=True
        ),
        "bugs": lambda rows: render_count_table(
            "Bug Hotspots", "Bug Commits", rows, repo_col=True
        ),
        "velocity": lambda rows: render_velocity(rows, repo_col=True),
        "firefighting": lambda rows: render_firefighting(rows, repo_col=True),
        "branches": lambda rows: render_branches(rows, repo_col=True),
    }

    keys = collectors if section == "all" else {section: collectors[section]}
    for i, key in enumerate(keys):
        if i > 0:
            console.print()
        renderers[key](collectors[key]())


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
@click.option("-C", "--scan", default=None, help="Scan directory tree for git repos.")
def main(since: str, limit: int, section: str, scan: str | None):
    """Survey a git repo: churn, contributors, bug hotspots, velocity, firefighting, and branches."""
    if not scan and not run("git rev-parse --git-dir"):
        scan = "."
    if scan:
        root = Path(scan).resolve()
        repos = find_repos(str(root))
        if not repos:
            console.print(f"[red]No git repos found under {root}")
            return
        _run_scan(since, limit, section, repos, root)
    else:
        _run_single(since, limit, section)


if __name__ == "__main__":
    main()
