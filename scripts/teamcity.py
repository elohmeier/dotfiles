"""Read TeamCity resources through its REST API."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from urllib.parse import quote, unquote, urlencode, urlsplit

import httpx
import rich_click as click


BUILD_FIELDS = (
    "id,buildTypeId,number,status,state,branchName,defaultBranch,webUrl,"
    "statusText,queuedDate,startDate,finishDate"
)
BUILD_TYPE_FIELDS = "id,name,projectId,projectName,paused,webUrl"


@dataclass(frozen=True)
class Config:
    url: str
    host: str | None
    token_command: str | None
    verify: bool
    timeout: float


def identifier(
    _ctx: click.Context, _param: click.Parameter, value: str | None
) -> str | None:
    if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise click.BadParameter("use a TeamCity ID, not a name, locator, or URL")
    return value


def token(config: Config) -> str:
    value = os.getenv("TEAMCITY_TOKEN")
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
        raise click.ClickException("set TEAMCITY_TOKEN or TEAMCITY_TOKEN_COMMAND")
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", value):
        raise click.ClickException("empty or invalid bearer token")
    return value


def rest_path(value: str) -> str:
    """Accept REST-relative paths and returned hrefs, never another origin."""
    parsed = urlsplit(value)
    decoded = unquote(parsed.path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise click.ClickException("get expects a REST path, not a URL or fragment")
    if (
        any(ord(char) < 32 or ord(char) == 127 for char in unquote(value))
        or "\\" in decoded
    ):
        raise click.ClickException("invalid character in REST path")
    if any(part in (".", "..") for part in decoded.split("/")):
        raise click.ClickException("REST path must not contain dot segments")
    path = parsed.path if parsed.path.startswith("/") else f"/app/rest/{parsed.path}"
    if not path.startswith("/app/rest/"):
        raise click.ClickException("get paths must be below /app/rest/")
    return quote(path, safe="/%:,@()$=") + (
        f"?{quote(parsed.query, safe='%&=:+,()$@/?')}" if parsed.query else ""
    )


def request(
    config: Config,
    path: str,
    params: list[tuple[str, str]] | None = None,
    *,
    accept: str = "application/json",
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token(config)}", "Accept": accept}
    extensions = None
    if config.host:
        headers["Host"] = config.host
        extensions = {"sni_hostname": config.host}
    if params:
        path += ("&" if "?" in path else "?") + urlencode(params)
    try:
        with httpx.Client(
            base_url=config.url,
            headers=headers,
            verify=config.verify,
            timeout=config.timeout,
        ) as client:
            response = client.get(path, extensions=extensions)
    except (httpx.HTTPError, OSError, subprocess.SubprocessError) as error:
        raise click.ClickException(str(error)) from error
    if not 200 <= response.status_code < 300:
        raise click.ClickException(f"HTTP {response.status_code}: request failed")
    return response


def emit(
    config: Config,
    path: str,
    params: list[tuple[str, str]] | None = None,
    *,
    raw: bool = False,
    accept: str = "application/json",
    output: Path | None = None,
) -> None:
    if output and output.exists():
        raise click.ClickException(f"output file already exists: {output}")
    response = request(config, path, params, accept=accept)
    if output:
        output.write_bytes(response.content)
    elif raw:
        sys.stdout.buffer.write(response.content)
    elif "json" not in response.headers.get("content-type", "").lower():
        raise click.ClickException("expected JSON; use get --raw for other content")
    else:
        click.echo(json.dumps(response.json(), indent=2, ensure_ascii=False))


def locator_params(
    *,
    limit: int | None = None,
    start: int = 0,
    fields: str | None = None,
    **dimensions: str | None,
) -> list[tuple[str, str]]:
    locator = [
        f"{key}:{value}" for key, value in dimensions.items() if value is not None
    ]
    if limit is not None:
        locator += [f"count:{limit}", f"start:{start}"]
    params = [("locator", ",".join(locator))] if locator else []
    if fields:
        params.append(("fields", fields))
    return params


def page_options(fields: str):
    def decorate(function):
        function = click.option("--fields", default=fields, show_default=True)(function)
        function = click.option(
            "--start", type=click.IntRange(min=0), default=0, show_default=True
        )(function)
        return click.option(
            "--limit", type=click.IntRange(min=1), default=25, show_default=True
        )(function)

    return decorate


@click.group()
@click.option("--url", envvar="TEAMCITY_URL", required=True, help="TeamCity base URL.")
@click.option(
    "--host", envvar="TEAMCITY_HOST", help="Host header and TLS SNI override."
)
@click.option("--token-command", envvar="TEAMCITY_TOKEN_COMMAND")
@click.option(
    "--verify/--no-verify", envvar="TEAMCITY_VERIFY", default=True, show_default=True
)
@click.option(
    "--timeout", envvar="TEAMCITY_TIMEOUT", type=float, default=60, show_default=True
)
@click.pass_context
def main(
    ctx: click.Context,
    url: str,
    host: str | None,
    token_command: str | None,
    verify: bool,
    timeout: float,
) -> None:
    """Read TeamCity projects, builds, tests, and artifacts."""
    ctx.obj = Config(url.rstrip("/"), host, token_command, verify, timeout)


@main.command()
@click.option("--fields", default="version,buildNumber,webUrl", show_default=True)
@click.pass_obj
def server(config: Config, fields: str) -> None:
    """Show the server version."""
    emit(config, "/app/rest/server", [("fields", fields)])


@main.command()
@click.option("--parent", callback=identifier)
@page_options("count,nextHref,project(id,name,parentProjectId,archived,webUrl)")
@click.pass_obj
def projects(
    config: Config, parent: str | None, limit: int, start: int, fields: str
) -> None:
    """List projects, optionally direct children of a project."""
    emit(
        config,
        "/app/rest/projects",
        locator_params(
            limit=limit,
            start=start,
            fields=fields,
            parentProject=f"(id:{parent})" if parent else None,
        ),
    )


@main.command()
@click.argument("id", callback=identifier)
@click.option(
    "--fields",
    default="id,name,parentProjectId,archived,webUrl,projects(count,project(id,name)),"
    "buildTypes(count,buildType(id,name))",
    show_default=True,
)
@click.pass_obj
def project(config: Config, id: str, fields: str) -> None:
    """Show a project and its immediate children."""
    emit(config, f"/app/rest/projects/id:{id}", [("fields", fields)])


@main.command("build-types")
@click.option("--project", required=True, callback=identifier)
@page_options(f"count,nextHref,buildType({BUILD_TYPE_FIELDS})")
@click.pass_obj
def build_types(
    config: Config, project: str, limit: int, start: int, fields: str
) -> None:
    """List build configurations in a project tree."""
    emit(
        config,
        "/app/rest/buildTypes",
        locator_params(
            limit=limit,
            start=start,
            fields=fields,
            affectedProject=f"(id:{project})",
        ),
    )


@main.command("build-type")
@click.argument("id", callback=identifier)
@click.option("--fields", default=BUILD_TYPE_FIELDS, show_default=True)
@click.pass_obj
def build_type(config: Config, id: str, fields: str) -> None:
    """Show build configuration metadata."""
    emit(config, f"/app/rest/buildTypes/id:{id}", [("fields", fields)])


def build_list(
    config: Config,
    path: str,
    project: str | None,
    build_type: str | None,
    limit: int,
    start: int,
    fields: str,
    dimensions: list[str] | None = None,
) -> None:
    values = dimensions or []
    if project:
        values.append(
            f"{'project' if path.endswith('buildQueue') else 'affectedProject'}:(id:{project})"
        )
    if build_type:
        values.append(f"buildType:(id:{build_type})")
    values += [f"count:{limit}", f"start:{start}"]
    emit(config, path, [("locator", ",".join(values)), ("fields", fields)])


@main.command()
@click.option("--project", callback=identifier)
@click.option("--build-type", callback=identifier)
@click.option("--branch")
@click.option(
    "--state", type=click.Choice(["any", "running", "finished"]), default="any"
)
@click.option("--status", type=click.Choice(["SUCCESS", "FAILURE", "UNKNOWN"]))
@page_options(f"count,nextHref,build({BUILD_FIELDS})")
@click.pass_obj
def builds(
    config: Config,
    project: str | None,
    build_type: str | None,
    branch: str | None,
    state: str,
    status: str | None,
    limit: int,
    start: int,
    fields: str,
) -> None:
    """List build history and running builds."""
    dimensions = ["defaultFilter:false", f"state:{state}"]
    if branch is None:
        dimensions.append("branch:default:any")
    else:
        encoded = base64.urlsafe_b64encode(branch.encode()).decode().rstrip("=")
        dimensions.append(f"branch:(name:($base64:{encoded}))")
    if status:
        dimensions.append(f"status:{status}")
    build_list(
        config,
        "/app/rest/builds",
        project,
        build_type,
        limit,
        start,
        fields,
        dimensions,
    )


@main.command()
@click.option("--project", callback=identifier)
@click.option("--build-type", callback=identifier)
@page_options(f"count,nextHref,build({BUILD_FIELDS})")
@click.pass_obj
def queue(
    config: Config,
    project: str | None,
    build_type: str | None,
    limit: int,
    start: int,
    fields: str,
) -> None:
    """List queued builds."""
    build_list(
        config, "/app/rest/buildQueue", project, build_type, limit, start, fields
    )


@main.command()
@click.argument("id", type=click.IntRange(min=1))
@click.option(
    "--fields",
    default=BUILD_FIELDS
    + ",buildType(id,name,projectId),agent(id,name),revisions(revision(version,vcsBranchName,"
    "vcs-root-instance(id,name))),snapshot-dependencies(build(id,buildTypeId,status,state)),"
    "problemOccurrences(count,problemOccurrence(id,type,details)),"
    "testOccurrences(count,passed,failed,ignored)",
    show_default=True,
)
@click.pass_obj
def build(config: Config, id: int, fields: str) -> None:
    """Show a build result, revisions, dependencies, and problems."""
    emit(config, f"/app/rest/builds/id:{id}", [("fields", fields)])


@main.command()
@click.argument("id", type=click.IntRange(min=1))
@click.option(
    "--fields",
    default="count,problemOccurrence(id,type,details,additionalData)",
    show_default=True,
)
@click.pass_obj
def problems(config: Config, id: int, fields: str) -> None:
    """Show build problem details."""
    emit(config, f"/app/rest/builds/id:{id}/problemOccurrences", [("fields", fields)])


@main.command()
@click.argument("id", type=click.IntRange(min=1))
@click.option(
    "--all", "all_tests", is_flag=True, help="Include passing and ignored tests."
)
@page_options("count,nextHref,testOccurrence(id,name,status,details,ignored,muted)")
@click.pass_obj
def tests(
    config: Config, id: int, all_tests: bool, limit: int, start: int, fields: str
) -> None:
    """List failed test occurrences by default."""
    dimensions = [f"build:(id:{id})", f"count:{limit}", f"start:{start}"]
    if not all_tests:
        dimensions.append("status:FAILURE")
    emit(
        config,
        "/app/rest/testOccurrences",
        [("locator", ",".join(dimensions)), ("fields", fields)],
    )


def artifact_path(build_id: int, path: str, mode: str) -> str:
    if path.startswith("/") or any(part in (".", "..") for part in path.split("/")):
        raise click.ClickException(
            "artifact path must be relative and contain no dot segments"
        )
    return f"/app/rest/builds/id:{build_id}/artifacts/{mode}/{quote(path, safe='/')}"


@main.command()
@click.argument("id", type=click.IntRange(min=1))
@click.argument("path", default="")
@click.pass_obj
def artifacts(config: Config, id: int, path: str) -> None:
    """List artifact directory contents."""
    emit(config, artifact_path(id, path, "children"))


@main.command()
@click.argument("id", type=click.IntRange(min=1))
@click.argument("path")
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.pass_obj
def artifact(config: Config, id: int, path: str, output: Path) -> None:
    """Download an artifact to a new local file."""
    emit(
        config,
        artifact_path(id, path, "content"),
        raw=True,
        accept="*/*",
        output=output,
    )


@main.command()
@click.argument("id", type=click.IntRange(min=1))
@click.option("--output", type=click.Path(path_type=Path))
@click.pass_obj
def log(config: Config, id: int, output: Path | None) -> None:
    """Download a full text build log."""
    emit(
        config,
        "/downloadBuildLog.html",
        [("buildId", str(id)), ("plain", "true")],
        raw=True,
        accept="text/plain",
        output=output,
    )


@main.command("get")
@click.argument("path")
@click.option("--param", multiple=True, metavar="KEY=VALUE")
@click.option("--fields")
@click.option("--raw", is_flag=True, help="Output response bytes.")
@click.pass_obj
def get_path(
    config: Config, path: str, param: tuple[str, ...], fields: str | None, raw: bool
) -> None:
    """GET a REST-relative path or nextHref."""
    params = []
    for item in param:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise click.ClickException("--param expects KEY=VALUE")
        params.append((key, value))
    if fields:
        params.append(("fields", fields))
    emit(
        config,
        rest_path(path),
        params,
        raw=raw,
        accept="*/*" if raw else "application/json",
    )


if __name__ == "__main__":
    main()
