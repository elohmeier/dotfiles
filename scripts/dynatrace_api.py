"""Call Dynatrace environment and cluster APIs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any
from urllib.parse import urlencode

import httpx
import rich_click as click


@dataclass(frozen=True)
class Config:
    url: str
    host: str | None
    environment_id: str | None
    token_command: str | None
    verify: bool
    timeout: float


def token(config: Config) -> str:
    value = os.getenv("DYNATRACE_TOKEN")
    if value is None and config.token_command:
        try:
            value = subprocess.run(
                shlex.split(config.token_command),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError) as error:
            raise click.ClickException("token command failed") from error
    if value is None:
        raise click.ClickException("set DYNATRACE_TOKEN or DYNATRACE_TOKEN_COMMAND")
    value = value.strip()
    if not value:
        raise click.ClickException("empty API token")
    return value


def endpoint_path(config: Config, endpoint: str, cluster: bool = False) -> str:
    if endpoint.startswith(("http://", "https://")):
        raise click.ClickException("pass an API path, not a full URL")
    endpoint = f"/{endpoint.lstrip('/')}"
    if endpoint.startswith("/e/") or cluster or endpoint.startswith("/api/cluster/"):
        return endpoint
    if config.environment_id and endpoint.startswith(("/api/", "/ui/", "/oauth2/")):
        return f"/e/{config.environment_id}{endpoint}"
    return endpoint


def body(
    data: str | None, data_file: str | None, raw: bool
) -> tuple[Any, bytes | None]:
    if data and data_file:
        raise click.ClickException("use either --data or --data-file")
    value = (
        sys.stdin.read()
        if data_file == "-"
        else Path(data_file).read_text()
        if data_file
        else data
    )
    if value is None:
        return None, None
    if raw:
        return None, value.encode()
    try:
        return json.loads(value), None
    except json.JSONDecodeError as error:
        raise click.ClickException(
            f"invalid JSON; pass --raw for text: {error}"
        ) from error


def request(
    config: Config,
    method: str,
    endpoint: str,
    *,
    cluster: bool = False,
    params: tuple[str, ...] = (),
    accept: str = "application/json",
    data: str | None = None,
    data_file: str | None = None,
    raw: bool = False,
    content_type: str = "application/json",
    output: Path | None = None,
    headers: bool = False,
    status: bool = False,
) -> None:
    query = []
    for item in params:
        key, separator, value = item.partition("=")
        if not separator:
            raise click.ClickException(f"--param expects KEY=VALUE, got {item!r}")
        query.append((key, value))
    json_body, content = body(data, data_file, raw)
    request_headers = {"Authorization": f"Api-Token {token(config)}", "Accept": accept}
    extensions = None
    if config.host:
        request_headers["Host"] = config.host
        extensions = {"sni_hostname": config.host}
    if content is not None:
        request_headers["Content-Type"] = content_type
    endpoint = endpoint_path(config, endpoint, cluster)
    if query:
        endpoint += ("&" if "?" in endpoint else "?") + urlencode(query)
    try:
        with httpx.Client(
            base_url=config.url,
            headers=request_headers,
            verify=config.verify,
            timeout=config.timeout,
        ) as client:
            response = client.request(
                method,
                endpoint,
                json=json_body,
                content=content,
                extensions=extensions,
            )
    except (httpx.HTTPError, OSError, subprocess.SubprocessError) as error:
        raise click.ClickException(str(error)) from error
    if status:
        click.echo(f"HTTP {response.status_code}", err=True)
    if headers:
        for key, value in response.headers.items():
            click.echo(f"{key}: {value}", err=True)
        click.echo(err=True)
    if output:
        output.write_bytes(response.content)
    elif "json" in response.headers.get("content-type", "").lower():
        click.echo(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        sys.stdout.buffer.write(response.content)
    if response.status_code >= 400:
        raise SystemExit(1)


@click.group()
@click.option(
    "--url", envvar="DYNATRACE_URL", required=True, help="Dynatrace base URL."
)
@click.option(
    "--host", envvar="DYNATRACE_HOST", help="Host header and TLS SNI override."
)
@click.option("--environment-id", envvar="DYNATRACE_ENVIRONMENT_ID")
@click.option("--token-command", envvar="DYNATRACE_TOKEN_COMMAND")
@click.option(
    "--verify/--no-verify", envvar="DYNATRACE_VERIFY", default=True, show_default=True
)
@click.option(
    "--timeout", envvar="DYNATRACE_TIMEOUT", type=float, default=60, show_default=True
)
@click.pass_context
def main(
    ctx: click.Context,
    url: str,
    host: str | None,
    environment_id: str | None,
    token_command: str | None,
    verify: bool,
    timeout: float,
) -> None:
    """Call Dynatrace APIs with configuration supplied by options or environment variables."""
    ctx.obj = Config(
        url.rstrip("/"), host, environment_id, token_command, verify, timeout
    )


def request_options(function):
    function = click.option(
        "--status", is_flag=True, help="Print HTTP status to stderr."
    )(function)
    function = click.option(
        "--headers", is_flag=True, help="Print response headers to stderr."
    )(function)
    function = click.option("--output", type=click.Path(path_type=Path))(function)
    function = click.option(
        "--content-type", default="application/json", show_default=True
    )(function)
    function = click.option("--raw", is_flag=True, help="Send the body as text.")(
        function
    )
    function = click.option("--data-file", type=click.Path(allow_dash=True))(function)
    function = click.option("--data")(function)
    function = click.option("--accept", default="application/json", show_default=True)(
        function
    )
    function = click.option("--param", "params", multiple=True, metavar="KEY=VALUE")(
        function
    )
    function = click.option(
        "--cluster", is_flag=True, help="Do not add the environment prefix."
    )(function)
    return function


def add_request_command(method: str) -> None:
    @main.command(method.lower())
    @click.argument("endpoint")
    @request_options
    @click.pass_obj
    def command(config: Config, endpoint: str, **options: Any) -> None:
        """Call a Dynatrace API endpoint."""
        request(config, method, endpoint, **options)


for request_method in ("GET", "POST", "PUT", "DELETE"):
    add_request_command(request_method)


@main.command("license-consumption")
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.option("--status", is_flag=True, help="Print HTTP status to stderr.")
@click.pass_obj
def license_consumption(config: Config, output: Path, status: bool) -> None:
    """Download the cluster-wide license consumption archive."""
    request(
        config,
        "GET",
        "/api/cluster/v2/license/consumption",
        cluster=True,
        accept="application/octet-stream",
        output=output,
        headers=True,
        status=status,
    )


if __name__ == "__main__":
    main()
