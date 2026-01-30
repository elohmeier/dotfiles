"""CyberArk PSM connection tool."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import tempfile
import webbrowser
from pathlib import Path

import questionary
import requests
import rich_click as click
from rich.console import Console
from rich.table import Table

console = Console(stderr=True)

CACHE_DIR = Path.home() / ".cache" / "cyberark-psm"

_verbose = False


def log(msg: str) -> None:
    if _verbose:
        console.print(f"[dim]{msg}[/dim]")


def api_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    if base.lower().endswith("/passwordvault"):
        base = base[: -len("/passwordvault")]
    return f"{base}/PasswordVault/API{path}"


def _token_path(url: str, user: str) -> Path:
    key = hashlib.sha256(f"{url}\0{user}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{key}.token"


def _load_cached_token(url: str, user: str) -> str | None:
    path = _token_path(url, user)
    if path.exists():
        log(f"Loaded cached token from {path}")
        return path.read_text().strip()
    log("No cached token found")
    return None


def _save_token(url: str, user: str, token: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _token_path(url, user)
    path.write_text(token)
    path.chmod(0o600)
    log(f"Saved token to {path}")


def _login(url: str, user: str, password: str, insecure: bool) -> str:
    login_url = api_url(url, "/Auth/LDAP/Logon")
    log(f"POST {login_url}")
    resp = requests.post(
        login_url,
        json={"username": user, "password": password, "concurrentSession": True},
        verify=not insecure,
    )
    if not resp.ok:
        raise click.ClickException(f"Login failed: {resp.status_code} {resp.reason}")
    log("Login successful")
    return resp.json()


def _get_session(ctx) -> requests.Session:
    if "session" not in ctx.obj:
        url = ctx.obj.get("url")
        if not url:
            raise click.UsageError("Missing option '--url' or CYBERARK_URL env var.")
        user = ctx.obj["user"]
        insecure = ctx.obj["insecure"]

        session = requests.Session()
        session.verify = not insecure

        # Try cached token first
        token = _load_cached_token(url, user)
        if token:
            session.headers["Authorization"] = token
            validate_url = api_url(url, "/Safes?limit=1")
            log(f"Validating cached token: GET {validate_url}")
            resp = session.get(validate_url)
            if resp.ok:
                log("Cached token valid")
                ctx.obj["session"] = session
                return session
            log(f"Cached token expired ({resp.status_code})")

        password = ctx.obj.get("password") or click.prompt("Password", hide_input=True)
        token = _login(url, user, password, insecure)
        _save_token(url, user, token)
        session.headers["Authorization"] = token
        ctx.obj["session"] = session
    return ctx.obj["session"]


def _search_accounts(
    session: requests.Session,
    url: str,
    query: str,
    safe: str | None = None,
    limit: int = 25,
) -> list[dict]:
    params: dict = {"search": query, "limit": limit}
    if safe:
        params["filter"] = f"safeName eq {safe}"
    req_url = api_url(url, "/Accounts")
    log(f"GET {req_url} params={params}")
    resp = session.get(req_url, params=params)
    if not resp.ok:
        raise click.ClickException(
            f"Account search failed: {resp.status_code} {resp.reason}"
        )
    accounts = resp.json().get("value", [])
    log(f"Found {len(accounts)} account(s)")
    return accounts


@click.group()
@click.option("--url", envvar="CYBERARK_URL", show_envvar=True, help="PVWA base URL.")
@click.option(
    "-u",
    "--user",
    envvar=["CYBERARK_USER", "USER"],
    show_envvar=True,
    help="Username.",
)
@click.option(
    "-p",
    "--password",
    envvar="CYBERARK_PASSWORD",
    show_envvar=True,
    help="Password (prompts if not set).",
)
@click.option("-k", "--insecure", is_flag=True, help="Skip TLS verification.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed progress.")
@click.pass_context
def cli(
    ctx, url: str | None, user: str, password: str | None, insecure: bool, verbose: bool
) -> None:
    """CyberArk PSM connection tool."""
    global _verbose
    _verbose = verbose
    ctx.ensure_object(dict)
    ctx.obj.update(url=url, user=user, password=password, insecure=insecure)


@cli.command()
@click.argument("query")
@click.option("-n", "--limit", default=25, help="Max results.")
@click.option("-s", "--safe", help="Filter by safe name.")
@click.pass_context
def search(ctx, query: str, limit: int, safe: str | None) -> None:
    """Search accounts."""
    session = _get_session(ctx)
    accounts = _search_accounts(session, ctx.obj["url"], query, safe, limit)
    table = Table(title="Accounts")
    for col in ("ID", "Username", "Address", "Safe", "Platform"):
        table.add_column(col)
    for a in accounts:
        table.add_row(
            a.get("id", ""),
            a.get("userName", ""),
            a.get("address", ""),
            a.get("safeName", ""),
            a.get("platformId", ""),
        )
    console.print(table)


def _looks_like_id(s: str) -> bool:
    return bool(re.fullmatch(r"[\d_]+", s))


def _build_autopost_html(psmgw_url: str, psmgw_request_b64: str) -> str:
    payload = json.loads(base64.b64decode(psmgw_request_b64))
    inputs = "\n".join(
        f'<input name="{html.escape(k)}" type="hidden" value="{html.escape(str(v))}">'
        for k, v in payload.items()
    )
    return (
        "<!doctype html><html><body>"
        f'<form id="psm" method="POST" action="{html.escape(psmgw_url)}">'
        f"{inputs}</form>"
        "<script>document.getElementById('psm').submit();</script>"
        "</body></html>"
    )


@cli.command()
@click.argument("id_or_query")
@click.option(
    "-c",
    "--component",
    required=True,
    envvar="CYBERARK_COMPONENT",
    show_envvar=True,
    help="PSM connection component.",
)
@click.option("-r", "--reason", help="Connection reason.")
@click.option(
    "-P",
    "--param",
    "params",
    multiple=True,
    help="Connection param key=value (repeatable).",
)
@click.pass_context
def connect(
    ctx,
    id_or_query: str,
    component: str,
    reason: str | None,
    params: tuple[str, ...],
) -> None:
    """Connect to account via PSM."""
    session = _get_session(ctx)
    url = ctx.obj["url"]

    if _looks_like_id(id_or_query):
        account_id = id_or_query
        log(f"Using {account_id} as account ID")
    else:
        accounts = _search_accounts(session, url, id_or_query)
        if not accounts:
            raise click.ClickException("No accounts found.")
        choices = [
            questionary.Choice(
                title=f"{a.get('userName', '')}@{a.get('address', '')} ({a.get('safeName', '')})",
                value=a["id"],
            )
            for a in accounts
        ]
        account_id = questionary.select("Select account:", choices=choices).ask()
        if not account_id:
            raise click.ClickException("No account selected.")

    body: dict = {"ConnectionComponent": component}
    if reason:
        body["reason"] = reason
    if params:
        body["ConnectionParams"] = {
            k: {"value": v, "ShouldSave": False}
            for p in params
            for k, v in [p.split("=", 1)]
        }
        log(f"ConnectionParams: {body['ConnectionParams']}")

    connect_url = api_url(url, f"/Accounts/{account_id}/PSMConnect")
    log(f"POST {connect_url}")
    resp = session.post(connect_url, json=body)
    if not resp.ok:
        raise click.ClickException(
            f"PSM connect failed: {resp.status_code} {resp.reason}"
        )
    data = resp.json()

    log(f"PSMGWURL: {data['PSMGWURL']}")
    page = _build_autopost_html(data["PSMGWURL"], data["PSMGWRequest"])
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(page.encode())
        webbrowser.open(f"file://{f.name}")
    console.print(f"Opening PSM session for account {account_id}...")


@cli.command()
@click.option("-s", "--search", "search_term", help="Search safes.")
@click.pass_context
def safes(ctx, search_term: str | None) -> None:
    """List accessible safes."""
    session = _get_session(ctx)
    params: dict = {"limit": 100}
    if search_term:
        params["search"] = search_term
    safes_url = api_url(ctx.obj["url"], "/Safes")
    log(f"GET {safes_url} params={params}")
    resp = session.get(safes_url, params=params)
    if not resp.ok:
        raise click.ClickException(
            f"Safes query failed: {resp.status_code} {resp.reason}"
        )
    table = Table(title="Safes")
    table.add_column("Safe Name")
    for s in resp.json().get("value", []):
        table.add_row(s.get("safeName", ""))
    console.print(table)


def main() -> None:
    cli(standalone_mode=True)


if __name__ == "__main__":
    main()
