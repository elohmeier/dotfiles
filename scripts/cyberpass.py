"""pass-like password manager CLI backed by CyberArk PVWA."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.tree import Tree

from scripts.cyberark_psm import (
    CACHE_DIR,
    _get_session,
    _load_settings,
    _resolve_password,
    api_url,
)

PATHS_CACHE = CACHE_DIR / "cyberpass-paths.json"
CLIP_TIME = int(os.environ.get("PASSWORD_STORE_CLIP_TIME", "45"))
FIELDS = {"login": "userName", "url": "address"}

console = Console()


class PassGroup(click.RichGroup):
    """Treat unknown first arguments as `show <path>`, like pass."""

    def parse_args(self, ctx, args):
        if args and not args[0].startswith("-") and args[0] not in self.commands:
            args = ["show", *args]
        return super().parse_args(ctx, args)


def _api(ctx, path: str, **kw):
    if "session" not in ctx.obj:
        ctx.obj["password"] = _resolve_password(
            ctx.obj["password"], ctx.obj["settings"]
        )
    resp = _get_session(ctx).request(
        kw.pop("method", "GET"), api_url(ctx.obj["url"], path), **kw
    )
    if not resp.ok:
        raise click.ClickException(
            f"{path}: {resp.status_code} {resp.reason} {resp.text[:200]}"
        )
    return resp.json() if resp.content else None


def _refresh(ctx) -> dict[str, str]:
    paths, offset = {}, 0
    while True:
        page = _api(ctx, "/Accounts", params={"limit": 1000, "offset": offset})["value"]
        paths |= {f"{a['safeName']}/{a['name']}": a["id"] for a in page}
        offset += len(page)
        if len(page) < 1000:
            break
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PATHS_CACHE.write_text(json.dumps(paths))
    return paths


def _paths(ctx) -> dict[str, str]:
    return (
        json.loads(PATHS_CACHE.read_text()) if PATHS_CACHE.exists() else _refresh(ctx)
    )


def _account_id(ctx, path: str) -> str:
    path = path.strip("/")
    account_id = _paths(ctx).get(path) or _refresh(ctx).get(path)
    if not account_id:
        raise click.ClickException(f"{path} is not in the password store.")
    return account_id


def _render(ctx, account_id: str, reason: str | None) -> tuple[dict, str]:
    account = _api(ctx, f"/Accounts/{account_id}")
    body = {"reason": reason} if reason else {}
    password = _api(
        ctx, f"/Accounts/{account_id}/Password/Retrieve", method="POST", json=body
    )
    lines = [password] + [
        f"{k}: {account[v]}" for k, v in FIELDS.items() if account.get(v)
    ]
    props = account.get("platformAccountProperties", {})
    lines += [f"{k}: {v}" for k, v in props.items()]
    return account, "\n".join(lines) + "\n"


def _parse(text: str) -> tuple[str, dict[str, str]]:
    password, *rest = text.splitlines() or [""]
    return password, dict(line.split(": ", 1) for line in rest if ": " in line)


def _field(key: str) -> str:
    return f"/{FIELDS.get(key) or 'platformAccountProperties/' + key}"


def _tree(title: str, paths) -> None:
    tree, nodes = Tree(f"[bold]{title}[/bold]"), {}
    for path in sorted(paths, key=str.lower):
        safe, name = path.split("/", 1)
        if safe not in nodes:
            nodes[safe] = tree.add(f"[bold blue]{safe}[/bold blue]")
        nodes[safe].add(name)
    console.print(tree)


def _clip(text: str) -> None:
    if sys.platform == "darwin":
        cmd = ["pbcopy"]
    elif os.environ.get("WAYLAND_DISPLAY"):
        cmd = ["wl-copy"]
    elif shutil.which("clip.exe"):
        cmd = ["clip.exe"]
    else:
        cmd = ["xclip", "-selection", "clipboard"]
    subprocess.run(cmd, input=text, text=True, check=True)
    subprocess.Popen(
        ["sh", "-c", f"sleep {CLIP_TIME}; printf '' | {shlex.join(cmd)}"],
        start_new_session=True,
    )


@click.group(cls=PassGroup, invoke_without_command=True)
@click.pass_context
def cli(ctx) -> None:
    """pass-like interface to CyberArk. Entries are addressed as SAFE/ACCOUNT.

    Configuration (URL, user, password command) is shared with `cyberark-psm config`.
    """
    settings = _load_settings()
    ctx.ensure_object(dict).update(
        url=os.environ.get("CYBERARK_URL") or settings.url,
        user=os.environ.get("CYBERARK_USER") or settings.user or os.environ.get("USER"),
        password=os.environ.get("CYBERARK_PASSWORD"),
        insecure=bool(os.environ.get("CYBERARK_INSECURE")),
        settings=settings,
    )
    if ctx.invoked_subcommand is None:
        ctx.invoke(ls)


@cli.command()
@click.argument("subfolder", required=False, default="")
@click.option(
    "--flat", is_flag=True, hidden=True, help="Print cached paths (completion)."
)
@click.pass_context
def ls(ctx, subfolder: str, flat: bool) -> None:
    """List entries, optionally limited to a safe."""
    if flat:
        click.echo("\n".join(_paths(ctx)))
        return
    prefix = subfolder.strip("/") + "/" if subfolder else ""
    _tree(subfolder or "CyberArk", [p for p in _refresh(ctx) if p.startswith(prefix)])


@cli.command()
@click.argument("names", nargs=-1, required=True)
@click.pass_context
def find(ctx, names: tuple[str, ...]) -> None:
    """List entries matching any of NAMES (case-insensitive)."""
    terms = [n.lower() for n in names]
    _tree(
        f"Search Terms: {' '.join(names)}",
        [p for p in _refresh(ctx) if any(t in p.lower() for t in terms)],
    )


reason_option = click.option(
    "-r", "--reason", envvar="CYBERPASS_REASON", help="Reason for password access."
)


@cli.command()
@click.argument("path")
@click.option(
    "-c",
    "--clip",
    is_flag=True,
    help=f"Copy password to clipboard, clear after {CLIP_TIME}s.",
)
@reason_option
@click.pass_context
def show(ctx, path: str, clip: bool, reason: str | None) -> None:
    """Show password and account properties of PATH."""
    _, text = _render(ctx, _account_id(ctx, path), reason)
    if clip:
        _clip(text.split("\n", 1)[0])
        click.echo(
            f"Copied {path} to clipboard. Will clear in {CLIP_TIME} seconds.", err=True
        )
    else:
        click.echo(text, nl=False)


@cli.command()
@click.argument("path")
@reason_option
@click.pass_context
def edit(ctx, path: str, reason: str | None) -> None:
    """Edit password (first line) and properties of PATH in $EDITOR."""
    account_id = _account_id(ctx, path)
    _, text = _render(ctx, account_id, reason)
    tmpdir = "/dev/shm" if Path("/dev/shm").is_dir() else None
    with tempfile.NamedTemporaryFile(
        "w+", suffix=".txt", prefix="cyberpass.", dir=tmpdir
    ) as f:
        f.write(text)
        f.flush()
        subprocess.run(
            [*shlex.split(os.environ.get("EDITOR", "vi")), f.name], check=True
        )
        new = Path(f.name).read_text()
    if new == text:
        click.echo("Password unchanged.", err=True)
        return
    (old_pw, old), (new_pw, fields) = _parse(text), _parse(new)
    if new_pw != old_pw:
        body = {"ChangeEntireGroup": True, "NewCredentials": new_pw}
        _api(ctx, f"/Accounts/{account_id}/Password/Update", method="POST", json=body)
    ops = [
        {"op": "replace" if k in old else "add", "path": _field(k), "value": v}
        for k, v in fields.items()
        if old.get(k) != v
    ] + [{"op": "remove", "path": _field(k)} for k in old.keys() - fields.keys()]
    if ops:
        _api(ctx, f"/Accounts/{account_id}", method="PATCH", json=ops)
    click.echo(f"Updated {path}.", err=True)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
