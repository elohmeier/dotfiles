import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

SKIP = {"node_modules", ".venv", "venv", ".terraform", ".direnv", "__pycache__"}


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=False, capture_output=True, text=True
    ).stdout


def find_repos(root: Path) -> list[Path]:
    repos = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames or ".git" in filenames:
            repos.append(Path(dirpath))
            dirnames.clear()
        else:
            dirnames[:] = [d for d in dirnames if d not in SKIP]
    return repos


def worktrees(repo: Path) -> list[Path]:
    out = git(repo, "worktree", "list", "--porcelain").splitlines()
    return [Path(line[9:]) for line in out if line.startswith("worktree ")] or [repo]


def status(path: Path) -> dict:
    s = {
        "path": path,
        "branch": "",
        "upstream": False,
        "ahead": 0,
        "behind": 0,
        "staged": 0,
        "modified": 0,
        "untracked": 0,
        "conflicts": 0,
        "mtime": 0.0,
    }
    files = []
    entries = iter(git(path, "status", "--porcelain=v2", "--branch", "-z").split("\0"))
    for e in entries:
        if e.startswith("# branch.head "):
            s["branch"] = e[14:]
        elif e.startswith("# branch.upstream "):
            s["upstream"] = True
        elif e.startswith("# branch.ab "):
            a, b = e[12:].split()
            s["ahead"], s["behind"] = int(a), -int(b)
        elif e[:2] in ("1 ", "2 "):
            xy = e[2:4]
            s["staged"] += xy[0] != "."
            s["modified"] += xy[1] != "."
            files.append(e.split(" ", 8 if e[0] == "1" else 9)[-1])
            if e[0] == "2":
                next(entries)
        elif e.startswith("u "):
            s["conflicts"] += 1
            files.append(e.split(" ", 10)[-1])
        elif e.startswith("? "):
            s["untracked"] += 1
            files.append(e[2:])
    s["mtime"] = max(
        ((path / f).stat().st_mtime for f in files if (path / f).exists()), default=0.0
    )
    if not s["upstream"] and s["branch"] != "(detached)":
        s["ahead"] = int(
            git(path, "rev-list", "--count", "HEAD", "--not", "--remotes") or 0
        )
    return s


def is_dirty(s: dict) -> bool:
    return any(s[k] for k in ("staged", "modified", "untracked", "conflicts", "ahead"))


def num(s: dict, k: str, style: str) -> str:
    return f"[{style}]{s[k]}[/]" if s[k] else ""


def ago(t: float) -> str:
    if not t:
        return ""
    d = time.time() - t
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if d >= secs:
            return f"{int(d // secs)}{unit} ago"
    return "now"


@click.command()
@click.argument(
    "root", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option(
    "-a", "--all", "show_all", is_flag=True, help="Also show clean worktrees."
)
def main(root: Path, show_all: bool) -> None:
    """Show dirty git worktrees (changes, untracked files, unpushed commits) below ROOT."""
    root = root.resolve()
    with ThreadPoolExecutor(16) as pool:
        paths = {
            p.resolve()
            for wts in pool.map(worktrees, find_repos(root))
            for p in wts
            if p.exists()
        }
        results = [s for s in pool.map(status, paths) if show_all or is_dirty(s)]
    results.sort(key=lambda s: s["mtime"], reverse=True)

    table = Table(
        box=None, header_style="bold", caption="+staged ~modified ?untracked !conflicts"
    )
    table.add_column("worktree", overflow="fold")
    table.add_column("branch", overflow="fold")
    for col in ("↑", "↓", "+", "~", "?", "!", "touched"):
        table.add_column(col, justify="right", no_wrap=True)
    for s in results:
        p = s["path"]
        table.add_row(
            str(p.relative_to(root)) if p.is_relative_to(root) else str(p),
            f"[cyan]{s['branch']}[/]" + ("" if s["upstream"] else " [dim](local)[/]"),
            num(s, "ahead", "green"),
            num(s, "behind", "red"),
            num(s, "staged", "green"),
            num(s, "modified", "yellow"),
            num(s, "untracked", "magenta"),
            num(s, "conflicts", "bold red"),
            f"[dim]{ago(s['mtime'])}[/]",
        )
    Console().print(table)


if __name__ == "__main__":
    main()
