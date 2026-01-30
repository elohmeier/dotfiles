"""Grafana user management tool."""

from __future__ import annotations

from datetime import datetime, timezone

import questionary
import requests
import rich_click as click
from rich.console import Console
from rich.table import Table

console = Console(stderr=True)


def _build_session(api_key, cookie, user, password):
    session = requests.Session()
    if api_key:
        session.headers["Authorization"] = f"Bearer {api_key}"
    elif cookie:
        session.cookies.set("grafana_session", cookie)
    elif password:
        session.auth = (user, password)
    else:
        raise click.UsageError(
            "Provide --api-key, --cookie, or --user/--password for authentication."
        )
    return session


def _fetch_all_users(session, url):
    users = []
    page = 1
    while True:
        resp = session.get(
            f"{url.rstrip('/')}/api/users/search",
            params={"perpage": 1000, "page": page},
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
@click.option("--url", envvar="GRAFANA_URL", required=True, help="Grafana base URL.")
@click.option("--api-key", envvar="GRAFANA_API_KEY", help="API key (Bearer token).")
@click.option("--cookie", envvar="GRAFANA_COOKIE", help="grafana_session cookie value.")
@click.option(
    "--user", envvar="GRAFANA_USER", default="admin", help="Basic auth username."
)
@click.option("--password", envvar="GRAFANA_PASSWORD", help="Basic auth password.")
@click.pass_context
def cli(ctx, url, api_key, cookie, user, password):
    """Grafana user management."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["session"] = _build_session(api_key, cookie, user, password)


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

    for uid in selected:
        resp = session.delete(f"{url.rstrip('/')}/api/admin/users/{uid}")
        if resp.ok:
            console.print(f"  Deleted user {uid}")
        else:
            console.print(
                f"  [red]Failed to delete user {uid}: {resp.status_code}[/red]"
            )

    console.print(f"\nDone. Deleted {len(selected)} user(s).")


def main():
    cli(standalone_mode=True)


if __name__ == "__main__":
    main()
