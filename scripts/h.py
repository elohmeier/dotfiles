"""Clone repositories into ~/repos and print their directory for shell navigation."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Never
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen

import click

CODE_ROOT = Path.home() / "repos"


def abort(message: str) -> Never:
    click.echo(Path.cwd())
    click.echo(message, err=True)
    raise SystemExit(1)


def output(*args: str) -> str:
    return subprocess.run(args, stdout=subprocess.PIPE, text=True).stdout.strip()


def url_path(url: str) -> Path:
    parsed = urlsplit(url)
    return CODE_ROOT / (parsed.hostname or "") / parsed.path.lstrip("/")


def find_repo(term: str) -> Path | None:
    found = None
    found_depth = -1
    for directory, children, _ in os.walk(CODE_ROOT):
        children.sort()
        path = Path(directory)
        depth = len(path.relative_to(CODE_ROOT).parts)
        name = path.name.lower() if term == term.lower() else path.name
        if name == term and depth > found_depth:
            found, found_depth = path, depth
        if depth >= 3:
            children.clear()
    return found


@click.command(
    add_help_option=False,
    context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.argument("term", required=False)
@click.argument("git_opts", nargs=-1, type=click.UNPROCESSED)
def main(term: str | None, git_opts: tuple[str, ...]) -> None:
    """Find or clone a repository, passing trailing options to git clone."""
    if term is None or term in ("-h", "--help"):
        abort("Usage: h (<name> | <repo>/<name> | <url>) [git opts]")

    # git config: h.rewrite = "<regex> <replacement>", h.svn = <svn URL prefix>
    for rule in output("git", "config", "--get-all", "h.rewrite").splitlines():
        pattern, replacement = rule.split(maxsplit=1)
        term = re.sub(pattern, replacement, term, count=1)
    svn = next(
        (
            p
            for p in output("git", "config", "--get-all", "h.svn").split()
            if term.startswith(p)
        ),
        None,
    )
    url = term
    if match := re.fullmatch(r"([\w.\-]+)/([\w.\-]+)", term):
        owner, repo = match.groups()
        try:
            with urlopen(f"https://api.github.com/repos/{owner}/{repo}") as response:
                info = json.load(response)
            owner, repo = info["owner"]["login"], info["name"]
        except HTTPError:
            pass
        url = f"git@github.com:{owner}/{repo}.git"
        path = CODE_ROOT / "github.com" / owner / repo
    elif svn:
        fetch = output("git", "ls-remote", "--get-url", term)
        url = output(
            "svn", "info", "--non-interactive", "--show-item", "repos-root-url", fetch
        )
        if not url:
            abort(f"{term} not found")
        svn = term[: len(term) - len(fetch) + len(url)]
        path = url_path(svn)
    elif "://" in term:
        path = url_path(term)
    elif match := re.fullmatch(r"git(?:ea)?@([^:]+):(.*)", term):
        path = CODE_ROOT / match[1] / match[2]
    elif re.fullmatch(r"[\w.\-]+", term):
        path = find_repo(term)
    else:
        abort(f"Unknown pattern for {term}")

    if path is None:
        abort(f"{term} not found")
    if path.suffix == ".git":
        path = path.with_suffix("")
    if not path.is_dir():
        missing = []
        parent = path.parent
        while not parent.is_dir():
            missing.append(parent)
            parent = parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        clone = (
            ["svn", "clone", f"--rewrite-root={svn}", *(git_opts or ("-r", "HEAD"))]
            if svn
            else ["clone", *(git_opts or ("--recursive",))]
        )
        result = subprocess.run(
            ["git", *clone, "--", url, str(path)], stdout=sys.stderr
        )
        if result.returncode:
            for parent in missing:
                parent.rmdir()
            raise SystemExit(result.returncode)
    click.echo(path)


if __name__ == "__main__":
    main()
