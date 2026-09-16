from __future__ import annotations

from types import SimpleNamespace

import httpx
import rich_click as click
from click.exceptions import Exit

from .alerts import (
    cmd_alert_rule_create,
    cmd_alert_rule_delete,
    cmd_alert_rule_edit,
    cmd_alert_rule_get,
    cmd_alert_rule_patch,
    cmd_alert_rule_reconcile_explore_links,
    cmd_alert_rule_replace,
)
from .api import (
    cmd_alert_rules,
    cmd_folders,
    cmd_list,
    cmd_metrics,
    cmd_query,
    cmd_show,
)
from .common import (
    ALERT_RULE_PATCH_CONTENT_TYPES,
    DEFAULT_QUERY_API_MAX_BODY_BYTES,
    GRAFANA_VERSION,
    SHOW_RESOURCES,
)
from .http import client
from .proxy import cmd_prom_api, cmd_query_api


@click.group()
@click.version_option(GRAFANA_VERSION, message="Grafana %(version)s")
@click.option(
    "--url",
    envvar="GRAFANA_URL",
    required=True,
    show_envvar=True,
    help="Grafana base URL.",
)
@click.option(
    "--token",
    envvar="GRAFANA_TOKEN",
    show_envvar=True,
    help="Bearer token.",
)
@click.option(
    "--username",
    envvar="GRAFANA_USERNAME",
    show_envvar=True,
    help="HTTP basic-auth username.",
)
@click.option(
    "--password",
    envvar="GRAFANA_PASSWORD",
    show_envvar=True,
    help="HTTP basic-auth password.",
)
@click.option(
    "--host",
    envvar="GRAFANA_HOST_HEADER",
    show_envvar=True,
    help="HTTP Host header override.",
)
@click.option(
    "--sni-hostname",
    envvar="GRAFANA_SNI_HOSTNAME",
    show_envvar=True,
    help="TLS SNI hostname override.",
)
@click.option(
    "--verify/--no-verify",
    envvar="GRAFANA_TLS_VERIFY",
    default=True,
    show_default=True,
    show_envvar=True,
    help="Verify the upstream TLS certificate.",
)
@click.option(
    "--timeout",
    envvar="GRAFANA_TIMEOUT",
    type=float,
    default=60.0,
    show_default=True,
    show_envvar=True,
    help="Upstream request timeout in seconds.",
)
@click.option("--ca-file", envvar="GRAFANA_CA_FILE", help="PEM CA bundle.")
@click.pass_context
def cli(
    ctx: click.Context,
    url: str,
    token: str | None,
    username: str | None,
    password: str | None,
    host: str | None,
    sni_hostname: str | None,
    verify: bool,
    timeout: float,
    ca_file: str | None,
) -> None:
    """Query Grafana datasources and alerting resources, with API facades."""
    grafana_client = client(
        url, token, username, password, host, sni_hostname, verify, timeout, ca_file
    )
    ctx.obj = grafana_client
    ctx.call_on_close(grafana_client.close)


def run_command(result: int) -> None:
    if result:
        raise Exit(result)


@cli.command("list")
@click.option("--type", "datasource_type", help="Filter by datasource type.")
@click.pass_obj
def list_command(c: httpx.Client, datasource_type: str | None) -> None:
    """List datasources."""
    run_command(cmd_list(c, SimpleNamespace(type=datasource_type)))


@cli.command("metrics")
@click.option("--uid", required=True, help="Datasource UID.")
@click.option(
    "--match",
    "matches",
    multiple=True,
    help="Series selector; repeat as needed.",
)
@click.option("--from", "start", help="Start time as RFC3339 or Unix time.")
@click.option("--to", "end", help="End time as RFC3339 or Unix time.")
@click.option("--grep", help="Client-side regular expression filter.")
@click.option("--limit", type=int, default=0, show_default=True)
@click.pass_obj
def metrics_command(
    c: httpx.Client,
    uid: str,
    matches: tuple[str, ...],
    start: str | None,
    end: str | None,
    grep: str | None,
    limit: int,
) -> None:
    """List Prometheus metric names."""
    run_command(
        cmd_metrics(
            c,
            SimpleNamespace(
                uid=uid,
                match=matches,
                start=start,
                end=end,
                grep=grep,
                limit=limit,
            ),
        )
    )


@cli.command("alert-rules")
@click.option("--folder-uid", help="Exact folder UID.")
@click.option("--group", multiple=True, help="Exact rule-group name; repeatable.")
@click.option("--rule", multiple=True, help="Exact rule title; repeatable.")
@click.option("--uid", multiple=True, help="Exact rule UID; repeatable.")
@click.option("--title", help="Case-insensitive rule-title substring.")
@click.option("--search-group", help="Case-insensitive group-name substring.")
@click.option("--search-folder", help="Case-insensitive folder-name substring.")
@click.option("--receiver", help="Receiver/contact-point name.")
@click.option("--datasource-uid", multiple=True, help="Datasource UID; repeatable.")
@click.option(
    "--state",
    multiple=True,
    type=click.Choice(
        (
            "normal",
            "inactive",
            "pending",
            "alerting",
            "firing",
            "nodata",
            "error",
            "recovering",
        )
    ),
    help="Rule state; repeatable.",
)
@click.option(
    "--health",
    multiple=True,
    type=click.Choice(("ok", "error", "nodata")),
    help="Rule health; repeatable.",
)
@click.option(
    "--type",
    "rule_type",
    type=click.Choice(("alerting", "recording")),
    help="Rule type.",
)
@click.option("--dashboard-uid", help="Dashboard UID.")
@click.option("--panel-id", type=int, help="Panel ID; requires --dashboard-uid.")
@click.option(
    "--label-matcher",
    multiple=True,
    help='JSON rule-label matcher, e.g. {"type":0,"name":"severity","value":"critical"}; repeatable.',
)
@click.option("--plugins", type=click.Choice(("hide", "only")))
@click.option("--group-limit", type=click.IntRange(min=0))
@click.option("--rule-limit", type=click.IntRange(min=0))
@click.option("--next-token", help="groupNextToken from a previous response.")
@click.option(
    "--limit-alerts",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="Maximum alert instances per rule.",
)
@click.pass_obj
def alert_rules_command(
    c: httpx.Client,
    folder_uid: str | None,
    group: tuple[str, ...],
    rule: tuple[str, ...],
    uid: tuple[str, ...],
    title: str | None,
    search_group: str | None,
    search_folder: str | None,
    receiver: str | None,
    datasource_uid: tuple[str, ...],
    state: tuple[str, ...],
    health: tuple[str, ...],
    rule_type: str | None,
    dashboard_uid: str | None,
    panel_id: int | None,
    label_matcher: tuple[str, ...],
    plugins: str | None,
    group_limit: int | None,
    rule_limit: int | None,
    next_token: str | None,
    limit_alerts: int,
) -> None:
    """Query Grafana-managed alert rules and their runtime state."""
    run_command(cmd_alert_rules(c, SimpleNamespace(**locals())))


@cli.group("alert-rule")
def alert_rule_group() -> None:
    """Manage editable App Platform alert rules."""


@alert_rule_group.command("get")
@click.argument("name")
@click.option("--namespace", default="default", show_default=True)
@click.pass_obj
def alert_rule_get_command(c: httpx.Client, name: str, namespace: str) -> None:
    """Get one editable App Platform alert rule as JSON."""
    run_command(cmd_alert_rule_get(c, SimpleNamespace(**locals())))


@alert_rule_group.command("create")
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
)
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_create_command(
    c: httpx.Client,
    file: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Create a grouped alert rule from a JSON or YAML App Platform resource."""
    run_command(cmd_alert_rule_create(c, SimpleNamespace(**locals())))


@alert_rule_group.command("reconcile-explore-links")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--datasource-uid",
    multiple=True,
    help="Only reconcile alerts using this datasource UID; repeat as needed.",
)
@click.option(
    "--check",
    is_flag=True,
    help="Make no changes and fail if an Explore link is stale or missing.",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Apply changes; without this option the command only previews them.",
)
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_reconcile_explore_links_command(
    c: httpx.Client,
    namespace: str,
    datasource_uid: tuple[str, ...],
    check: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Reconcile generated Explore links for Elasticsearch alert rules."""
    run_command(cmd_alert_rule_reconcile_explore_links(c, SimpleNamespace(**locals())))


@alert_rule_group.command("replace")
@click.argument("name")
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
)
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_replace_command(
    c: httpx.Client,
    name: str,
    file: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Replace an alert rule from a JSON or YAML App Platform resource."""
    run_command(cmd_alert_rule_replace(c, SimpleNamespace(**locals())))


@alert_rule_group.command("patch")
@click.argument("name")
@click.argument(
    "file",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
)
@click.option(
    "--type",
    "patch_type",
    type=click.Choice(tuple(ALERT_RULE_PATCH_CONTENT_TYPES)),
    default="merge",
    show_default=True,
)
@click.option("--field-manager", default="grafana-query", show_default=True)
@click.option("--force", is_flag=True, help="Take field ownership for apply patches.")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_patch_command(
    c: httpx.Client,
    name: str,
    file: str,
    patch_type: str,
    field_manager: str,
    force: bool,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Patch an alert rule with merge, JSON, or server-side apply."""
    run_command(cmd_alert_rule_patch(c, SimpleNamespace(**locals())))


@alert_rule_group.command("edit")
@click.argument("name")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_edit_command(
    c: httpx.Client,
    name: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Edit one alert rule in $EDITOR, show a diff, and update it."""
    run_command(cmd_alert_rule_edit(c, SimpleNamespace(**locals())))


@alert_rule_group.command("delete")
@click.argument("name")
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate locally without sending a write request.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--allow-managed", is_flag=True)
@click.pass_obj
def alert_rule_delete_command(
    c: httpx.Client,
    name: str,
    namespace: str,
    dry_run: bool,
    yes: bool,
    allow_managed: bool,
) -> None:
    """Delete one alert rule."""
    run_command(cmd_alert_rule_delete(c, SimpleNamespace(**locals())))


@cli.command("show")
@click.argument("resource", type=click.Choice(SHOW_RESOURCES))
@click.option("--namespace", default="default", show_default=True)
@click.option(
    "--name",
    help="Exact App Platform resource name, or folder UID.",
)
@click.option("--limit", type=click.IntRange(min=1), default=1000, show_default=True)
@click.option("--continue-token", help="App Platform list continuation token.")
@click.option("--field-selector", help="App Platform field selector.")
@click.option("--label-selector", help="App Platform label selector.")
@click.option("--query", help="Team-name search query.")
@click.option("--page", type=click.IntRange(min=1), default=1, show_default=True)
@click.pass_obj
def show_command(
    c: httpx.Client,
    resource: str,
    namespace: str,
    name: str | None,
    limit: int,
    continue_token: str | None,
    field_selector: str | None,
    label_selector: str | None,
    query: str | None,
    page: int,
) -> None:
    """Show an allow-listed read-only Grafana resource as JSON."""
    run_command(cmd_show(c, SimpleNamespace(**locals())))


@cli.command("folders")
@click.option("--uid", help="Show only this folder subtree.")
@click.option(
    "--depth",
    type=click.IntRange(min=0),
    help="Maximum child-folder depth; omit for the complete subtree.",
)
@click.option("--dashboards", is_flag=True, help="Include dashboards as leaves.")
@click.option("--json", "json_output", is_flag=True, help="Output nested JSON.")
@click.pass_obj
def folders_command(
    c: httpx.Client,
    uid: str | None,
    depth: int | None,
    dashboards: bool,
    json_output: bool,
) -> None:
    """Explore the dashboard folder hierarchy."""
    run_command(cmd_folders(c, SimpleNamespace(**locals())))


@cli.command("query")
@click.option("--uid", help="Datasource UID.")
@click.option("--expr", help="Prometheus or Loki expression.")
@click.option("--sql", help="Raw SQL.")
@click.option("--lucene", help="Elasticsearch Lucene query.")
@click.option(
    "--agg",
    type=click.Choice(("logs", "count")),
    default="logs",
    show_default=True,
)
@click.option("--limit", type=int, default=100, show_default=True)
@click.option("--time-field", default="@timestamp", show_default=True)
@click.option(
    "--target",
    type=click.Path(exists=True, dir_okay=False, allow_dash=True),
    help="Panel target JSON file or - for standard input.",
)
@click.option("--from", "start", default="now-5m", show_default=True)
@click.option("--to", "end", default="now", show_default=True)
@click.option("--instant", is_flag=True, help="Run an instant query.")
@click.option("--step", help="Range step, such as 30s, 1m, or 500ms.")
@click.pass_obj
def query_command(
    c: httpx.Client,
    uid: str | None,
    expr: str | None,
    sql: str | None,
    lucene: str | None,
    agg: str,
    limit: int,
    time_field: str,
    target: str | None,
    start: str,
    end: str,
    instant: bool,
    step: str | None,
) -> None:
    """Run one datasource query."""
    run_command(
        cmd_query(
            c,
            SimpleNamespace(
                uid=uid,
                expr=expr,
                sql=sql,
                lucene=lucene,
                agg=agg,
                limit=limit,
                time_field=time_field,
                target=target,
                start=start,
                end=end,
                instant=instant,
                step=step,
            ),
        )
    )


@cli.command("prom-api")
@click.option("--uid", required=True, help="Prometheus datasource UID.")
@click.option("--listen", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=19090, show_default=True)
@click.option("--no-type-check", is_flag=True)
@click.option("--no-ui", is_flag=True, help="Disable the live terminal dashboard.")
@click.option("--quiet", is_flag=True)
@click.pass_obj
def prom_api_command(
    c: httpx.Client,
    uid: str,
    listen: str,
    port: int,
    no_type_check: bool,
    no_ui: bool,
    quiet: bool,
) -> None:
    """Serve a local Prometheus API facade backed by Grafana."""
    run_command(
        cmd_prom_api(
            c,
            SimpleNamespace(
                uid=uid,
                listen=listen,
                port=port,
                no_type_check=no_type_check,
                no_ui=no_ui,
                quiet=quiet,
            ),
        )
    )


@cli.command("query-api")
@click.option(
    "--uid",
    multiple=True,
    required=True,
    help="Allowed datasource UID; repeat as needed.",
)
@click.option(
    "--elasticsearch-uid",
    multiple=True,
    help="Read-only Elasticsearch datasource UID; repeat as needed.",
)
@click.option("--rqlite-uid", help="Read-only rqlite datasource UID.")
@click.option(
    "--prometheus-uid",
    multiple=True,
    help="Prometheus datasource UID; repeat as needed.",
)
@click.option("--listen", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=19080, show_default=True)
@click.option(
    "--max-body-bytes",
    type=int,
    default=DEFAULT_QUERY_API_MAX_BODY_BYTES,
    show_default=True,
)
@click.option(
    "--cors-origin",
    multiple=True,
    default=("http://localhost:3000", "http://127.0.0.1:3000"),
    show_default=True,
    help="Allowed browser origin; repeat as needed.",
)
@click.option("--no-uid-check", is_flag=True)
@click.option("--no-ui", is_flag=True, help="Disable the live terminal dashboard.")
@click.option("--quiet", is_flag=True)
@click.pass_obj
def query_api_command(
    c: httpx.Client,
    uid: tuple[str, ...],
    elasticsearch_uid: tuple[str, ...],
    rqlite_uid: str | None,
    prometheus_uid: tuple[str, ...],
    listen: str,
    port: int,
    max_body_bytes: int,
    cors_origin: tuple[str, ...],
    no_uid_check: bool,
    no_ui: bool,
    quiet: bool,
) -> None:
    """Serve an allow-listed local Grafana query API."""
    run_command(
        cmd_query_api(
            c,
            SimpleNamespace(
                uid=uid,
                elasticsearch_uid=elasticsearch_uid,
                rqlite_uid=rqlite_uid,
                prometheus_uid=prometheus_uid,
                listen=listen,
                port=port,
                max_body_bytes=max_body_bytes,
                cors_origin=cors_origin,
                no_uid_check=no_uid_check,
                no_ui=no_ui,
                quiet=quiet,
            ),
        )
    )


def main() -> None:
    cli()
