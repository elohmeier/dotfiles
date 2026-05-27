"""Trigger Foreman remote-execution jobs."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests
import rich_click as click
import yaml
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

console = Console(stderr=True)

HAMMER_CONFIG = Path.home() / ".hammer" / "cli_config.yml"


def _load_hammer() -> dict:
    if not HAMMER_CONFIG.exists():
        return {}
    data = yaml.safe_load(HAMMER_CONFIG.read_text()) or {}
    return data.get(":foreman", {}) or {}


def _session(
    token: str | None, user: str | None, password: str | None
) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    elif user and password:
        s.auth = (user, password)
    else:
        raise click.UsageError(
            "No credentials. Set FOREMAN_TOKEN, or FOREMAN_USER+FOREMAN_PASSWORD, "
            f"or configure {HAMMER_CONFIG}."
        )
    return s


def _build_query(hosts: tuple[str, ...]) -> str:
    if len(hosts) == 1:
        return f"name = {hosts[0]}"
    return f"name ^ ({', '.join(hosts)})"


@click.command()
@click.argument("hosts", nargs=-1, required=True)
@click.option(
    "--url",
    envvar="FOREMAN_URL",
    help="Foreman base URL (env FOREMAN_URL, else hammer :host).",
)
@click.option(
    "--org-id",
    envvar="FOREMAN_ORG_ID",
    type=int,
    required=True,
    help="Organization id (env FOREMAN_ORG_ID).",
)
@click.option(
    "--token", envvar="FOREMAN_TOKEN", help="Personal Access Token (env FOREMAN_TOKEN)."
)
@click.option(
    "--user",
    envvar="FOREMAN_USER",
    help="Basic-auth user (env FOREMAN_USER, else hammer :username).",
)
@click.option(
    "--password",
    envvar="FOREMAN_PASSWORD",
    help="Basic-auth password (env FOREMAN_PASSWORD, else hammer :password).",
)
@click.option(
    "--template-id",
    type=int,
    default=421,
    show_default=True,
    help="Job template id (421 = Puppet Run Once).",
)
@click.option("--effective-user", default="remex", show_default=True)
@click.option("--timeout-interval", type=int, default=600, show_default=True)
@click.option("--description", default="Run Puppet once", show_default=True)
@click.option("--wait/--no-wait", default=True)
@click.option("--poll-interval", type=float, default=5.0, show_default=True)
def main(
    hosts,
    url,
    org_id,
    token,
    user,
    password,
    template_id,
    effective_user,
    timeout_interval,
    description,
    wait,
    poll_interval,
):
    hammer = _load_hammer()
    url = url or hammer.get(":host")
    user = user or hammer.get(":username")
    password = password or hammer.get(":password")
    if not url:
        raise click.UsageError(
            f"No Foreman URL. Set FOREMAN_URL or configure {HAMMER_CONFIG}."
        )

    url = url.rstrip("/")
    s = _session(token, user, password)
    payload = {
        "organization": {"id": org_id},
        "job_invocation": {
            "job_template_id": template_id,
            "targeting_type": "static_query",
            "search_query": _build_query(hosts),
            "inputs": {},
            "ssh": {"effective_user": effective_user},
            "description_format": description,
            "execution_timeout_interval": timeout_interval,
            "concurrency_control": {"concurrency_level": ""},
        },
    }
    r = s.post(f"{url}/api/job_invocations", json=payload)
    r.raise_for_status()
    jid = r.json()["id"]
    console.print(f"[green]Job {jid}[/] queued for {len(hosts)} host(s)")
    console.print(f"URL: {url}/job_invocations/{jid}")

    if not wait:
        return

    columns = [
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn(
            "[green]ok={task.fields[ok]}[/] "
            "[red]fail={task.fields[fail]}[/] "
            "[yellow]pend={task.fields[pend]}[/]"
        ),
        TimeElapsedColumn(),
    ]
    warned_empty = False
    with Progress(*columns, console=console, transient=False) as prog:
        task = prog.add_task("queued", total=None, ok=0, fail=0, pend=0)
        while True:
            r = s.get(
                f"{url}/api/job_invocations/{jid}", params={"host_status": "true"}
            )
            r.raise_for_status()
            d = r.json()
            status = d["status_label"]
            total = d["total"]
            done = d["succeeded"] + d["failed"] + d["cancelled"]
            prog.update(
                task,
                description=status,
                total=total or None,
                completed=done,
                ok=d["succeeded"],
                fail=d["failed"],
                pend=d["pending"],
            )
            if total == 0 and not warned_empty:
                console.print(
                    "[yellow]warn:[/] search matched 0 hosts — check hostname (try FQDN)"
                )
                warned_empty = True
            if status in ("succeeded", "failed", "cancelled"):
                sys.exit(0 if status == "succeeded" else 1)
            time.sleep(poll_interval)


if __name__ == "__main__":
    main()
