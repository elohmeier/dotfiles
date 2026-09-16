"""Grafana user management tool."""

from __future__ import annotations

from datetime import datetime, timezone

import questionary
import rich_click as click
from rich.console import Console
from rich.table import Table

from .common import GRAFANA_VERSION, REQUEST_EXTENSIONS
from .http import client

console = Console(stderr=True)


def _fetch_all_users(session, url):
    users = []
    page = 1
    while True:
        resp = session.get(
            f"{url.rstrip('/')}/api/users/search",
            params={"perpage": 1000, "page": page},
            extensions=REQUEST_EXTENSIONS,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("users", [])
        if not batch:
            break
        users.extend(batch)
        if len(users) >= data.get("totalCount", 0):
            break
        page += 1
    return users


def _days_ago(iso_str):
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def _users_table(users, title="Users"):
    table = Table(title=title)
    for col in ("ID", "Login", "Email", "Name", "Admin", "Last Seen", "Days Ago"):
        table.add_column(col)
    for u in users:
        days = _days_ago(u["lastSeenAt"])
        table.add_row(
            str(u["id"]),
            u.get("login", ""),
            u.get("email", ""),
            u.get("name", ""),
            str(u.get("isAdmin", False)),
            u.get("lastSeenAt", "")[:10],
            str(days),
        )
    return table


@click.group()
@click.version_option(GRAFANA_VERSION, message="Grafana %(version)s")
@click.option("--url", envvar="GRAFANA_URL", required=True, help="Grafana base URL.")
@click.option(
    "--username",
    envvar="GRAFANA_USERNAME",
    default="admin",
    help="Server administrator username.",
)
@click.option(
    "--password",
    envvar="GRAFANA_PASSWORD",
    required=True,
    help="Server administrator password.",
)
@click.option("--verify/--no-verify", envvar="GRAFANA_TLS_VERIFY", default=True)
@click.option("--ca-file", envvar="GRAFANA_CA_FILE", help="PEM CA bundle.")
@click.option("--host", envvar="GRAFANA_HOST_HEADER")
@click.option("--sni-hostname", envvar="GRAFANA_SNI_HOSTNAME")
@click.option("--timeout", envvar="GRAFANA_TIMEOUT", default=60.0)
@click.pass_context
def cli(ctx, url, username, password, verify, ca_file, host, sni_hostname, timeout):
    """Grafana server-wide user administration (Basic authentication)."""
    session = client(
        url, None, username, password, host, sni_hostname, verify, timeout, ca_file
    )
    ctx.obj = {"url": url, "session": session}
    ctx.call_on_close(session.close)


@cli.command("list")
@click.pass_context
def list_users(ctx):
    """List all Grafana users sorted by last seen."""
    users = _fetch_all_users(ctx.obj["session"], ctx.obj["url"])
    users.sort(key=lambda u: u.get("lastSeenAt", ""))
    console.print(_users_table(users))
    console.print(f"\nTotal: {len(users)} users")


@cli.command()
@click.option(
    "--min-days", required=True, type=int, help="Minimum inactivity threshold in days."
)
@click.option("--max-days", type=int, help="Maximum inactivity threshold in days.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
@click.pass_context
def delete(ctx, min_days, max_days, yes):
    """Delete inactive non-admin users."""
    session = ctx.obj["session"]
    url = ctx.obj["url"]
    users = _fetch_all_users(session, url)

    candidates = [
        u
        for u in users
        if not u.get("isAdmin")
        and min_days < _days_ago(u["lastSeenAt"]) <= (max_days or float("inf"))
    ]
    candidates.sort(key=lambda u: u.get("lastSeenAt", ""))

    if not candidates:
        console.print(f"No non-admin users inactive for more than {min_days} days.")
        return

    console.print(
        _users_table(candidates, title=f"Inactive > {min_days} days (non-admin)")
    )

    if not yes:
        choices = [
            questionary.Choice(
                title=f"{u['login']} ({u.get('email', '')}) - {_days_ago(u['lastSeenAt'])}d ago",
                value=u["id"],
                checked=True,
            )
            for u in candidates
        ]
        selected = questionary.checkbox(
            "Select users to delete:", choices=choices
        ).ask()
        if not selected:
            console.print("No users selected.")
            return
        if not questionary.confirm(
            f"Delete {len(selected)} user(s)?", default=False
        ).ask():
            console.print("Aborted.")
            return
    else:
        selected = [u["id"] for u in candidates]

    deleted = 0
    for uid in selected:
        resp = session.delete(
            f"{url.rstrip('/')}/api/admin/users/{uid}", extensions=REQUEST_EXTENSIONS
        )
        if resp.is_success:
            deleted += 1
            console.print(f"  Deleted user {uid}")
        else:
            console.print(
                f"  [red]Failed to delete user {uid}: {resp.status_code}[/red]"
            )

    console.print(f"\nDone. Deleted {deleted} of {len(selected)} selected user(s).")

    if deleted != len(selected):
        raise click.ClickException("Some users could not be deleted")


def main():
    cli(standalone_mode=True)


if __name__ == "__main__":
    main()
