"""CyberArk PSM connection tool."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import shlex
import subprocess
import tempfile
import webbrowser
from pathlib import Path

import questionary
import requests
import rich_click as click
from pydantic_settings import BaseSettings
from rich.console import Console
from rich.table import Table

console = Console(stderr=True)

CONFIG_DIR = Path.home() / ".config" / "cyberark-psm"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = Path.home() / ".cache" / "cyberark-psm"
ACCOUNTS_CACHE = CACHE_DIR / "accounts.json"

_verbose = False


def log(msg: str) -> None:
    if _verbose:
        console.print(f"[dim]{msg}[/dim]")


# --- Settings ---


class Settings(BaseSettings):
    url: str | None = None
    user: str | None = None
    password_cmd: str | None = None
    component: str | None = None


def _load_settings() -> Settings:
    if CONFIG_FILE.exists():
        return Settings.model_validate_json(CONFIG_FILE.read_text())
    return Settings()


def _save_settings(settings: Settings) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(settings.model_dump_json(indent=2, exclude_none=True))


def _resolve_password(password: str | None, settings: Settings) -> str | None:
    if password:
        return password
    if settings.password_cmd:
        log(f"Running password command: {settings.password_cmd}")
        result = subprocess.run(
            shlex.split(settings.password_cmd),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    return None


# --- API helpers ---


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
        detail = (resp.text or "")[:200].strip()
        msg = f"Login failed: {resp.status_code} {resp.reason}"
        if detail:
            msg += f"\n{detail}"
        raise click.ClickException(msg)
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


# --- Account ID cache ---


def _load_accounts_cache() -> dict[str, str]:
    if ACCOUNTS_CACHE.exists():
        return json.loads(ACCOUNTS_CACHE.read_text())
    return {}


def _save_accounts_cache(cache: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_CACHE.write_text(json.dumps(cache))


def _resolve_account_id(session: requests.Session, url: str, id_or_query: str) -> str:
    if re.fullmatch(r"[\d_]+", id_or_query):
        log(f"Using {id_or_query} as account ID")
        return id_or_query

    # Check account ID cache
    cache = _load_accounts_cache()
    if id_or_query in cache:
        account_id = cache[id_or_query]
        log(f"Cached account ID for '{id_or_query}': {account_id}")
        return account_id

    accounts = _search_accounts(session, url, id_or_query)
    if not accounts:
        raise click.ClickException(f"No accounts found for '{id_or_query}'.")

    if len(accounts) == 1:
        account_id = accounts[0]["id"]
        log(f"Auto-selected {account_id} ({accounts[0].get('userName', '')})")
        cache[id_or_query] = account_id
        _save_accounts_cache(cache)
        return account_id

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
    cache[id_or_query] = account_id
    _save_accounts_cache(cache)
    return account_id


# --- CLI ---


@click.group()
@click.option("--url", envvar="CYBERARK_URL", show_envvar=True, help="PVWA base URL.")
@click.option(
    "-u",
    "--user",
    envvar="CYBERARK_USER",
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
    ctx,
    url: str | None,
    user: str | None,
    password: str | None,
    insecure: bool,
    verbose: bool,
) -> None:
    """CyberArk PSM connection tool."""
    global _verbose
    _verbose = verbose
    ctx.ensure_object(dict)

    settings = _load_settings()
    url = url or settings.url
    user = user or settings.user or os.environ.get("USER")
    password = _resolve_password(password, settings)

    ctx.obj.update(
        url=url,
        user=user,
        password=password,
        insecure=insecure,
        settings=settings,
    )


@cli.command()
@click.option("--url", "cfg_url", help="PVWA base URL.")
@click.option("--user", "cfg_user", help="Username.")
@click.option("--password-cmd", help="Shell command to get password.")
@click.option("--component", help="Default PSM connection component.")
@click.pass_context
def config(
    ctx,
    cfg_url: str | None,
    cfg_user: str | None,
    password_cmd: str | None,
    component: str | None,
) -> None:
    """Show or update stored configuration."""
    settings = _load_settings()
    updates = {
        k: v
        for k, v in {
            "url": cfg_url,
            "user": cfg_user,
            "password_cmd": password_cmd,
            "component": component,
        }.items()
        if v is not None
    }
    if updates:
        merged = settings.model_dump()
        merged.update(updates)
        settings = Settings(**merged)
        _save_settings(settings)
        console.print("Configuration saved.")
    table = Table(title=f"Config ({CONFIG_FILE})")
    table.add_column("Key")
    table.add_column("Value")
    for k, v in settings.model_dump().items():
        table.add_row(k, str(v) if v else "[dim]not set[/dim]")
    console.print(table)


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
    component: str | None,
    reason: str | None,
    params: tuple[str, ...],
) -> None:
    """Connect to account via PSM."""
    component = component or ctx.obj["settings"].component
    if not component:
        raise click.UsageError(
            "Missing option '-c' / '--component' (no default in config)."
        )

    session = _get_session(ctx)
    url = ctx.obj["url"]
    account_id = _resolve_account_id(session, url, id_or_query)

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
