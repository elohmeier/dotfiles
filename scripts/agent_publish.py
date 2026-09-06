"""Publish project artifacts through one shared static document root."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import quote, urlsplit

import rich_click as click

APP_NAME = "agent-publish"
STATE_VERSION = 1
DEFAULT_URL = "http://localhost:8064"
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def data_root() -> Path:
    return Path.home() / ".local/share" / APP_NAME


def state_path() -> Path:
    return Path.home() / ".local/state" / APP_NAME / "state.json"


def empty_state() -> dict[str, object]:
    return {"version": STATE_VERSION, "projects": {}}


def load_state() -> dict[str, object]:
    path = state_path()
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise click.ClickException(f"invalid state file {path}: {error}") from error
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise click.ClickException(f"unsupported state file: {path}")
    if not isinstance(state.get("projects"), dict):
        raise click.ClickException(f"invalid projects in state file: {path}")
    return state


def save_state(state: dict[str, object]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            json.dump(state, output, indent=2, ensure_ascii=False, sort_keys=True)
            output.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise click.UsageError("project name does not produce a usable slug")
    return slug


def validate_slug(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug):
        raise click.UsageError(
            "slug must contain lowercase letters, digits, and internal hyphens"
        )
    return slug


def project_records(state: dict[str, object]) -> dict[str, dict[str, object]]:
    projects = state["projects"]
    if not isinstance(projects, dict):
        raise click.ClickException("invalid project registry")
    if not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in projects.items()
    ):
        raise click.ClickException("invalid project registry")
    return cast(dict[str, dict[str, object]], projects)


def asset_records(project: dict[str, object]) -> dict[str, str]:
    assets = project.setdefault("assets", {})
    if not isinstance(assets, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in assets.items()
    ):
        raise click.ClickException("invalid managed assets in project registry")
    return cast(dict[str, str], assets)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def select_project(
    state: dict[str, object], selector: str | None
) -> tuple[str, dict[str, object]]:
    projects = project_records(state)
    if selector in projects:
        return selector, projects[selector]  # type: ignore[index]

    candidate = Path(selector or Path.cwd()).expanduser().resolve()
    matches = [
        (slug, project)
        for slug, project in projects.items()
        if is_within(candidate, Path(cast(str, project["source"])))
    ]
    if not matches:
        shown = selector or str(Path.cwd())
        raise click.UsageError(f"no registered project matches {shown}")
    return max(matches, key=lambda item: len(Path(cast(str, item[1]["source"])).parts))


def project_dir(slug: str) -> Path:
    return data_root() / slug


def normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise click.UsageError("URL must be an absolute HTTP or HTTPS URL")
    if parsed.query or parsed.fragment:
        raise click.UsageError("URL must not contain a query or fragment")
    return value.rstrip("/")


def project_url(
    slug: str,
    relative: Path | None = None,
    state: dict[str, object] | None = None,
) -> str:
    parts = [quote(slug)]
    if relative is not None:
        parts.extend(quote(part) for part in relative.parts)
    suffix = "/".join(parts)
    if relative is None:
        suffix += "/"
    configured = os.environ.get("AGENT_PUBLISH_URL")
    if configured is None and state is not None:
        configured = cast(str | None, state.get("url"))
    return f"{normalize_url(configured or DEFAULT_URL)}/{suffix}"


def asset_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise click.UsageError("asset paths must be relative to the project directory")
    resolved = (root / relative).resolve()
    if not is_within(resolved, root.resolve()):
        raise click.UsageError(f"asset path leaves the project directory: {value}")
    return resolved


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Publish files from registered projects through the shared Caddy service."""


@cli.command()
@click.argument("source", type=click.Path(path_type=Path, file_okay=False), default=".")
@click.option("--slug")
@click.option("--name")
def register(source: Path, slug: str | None, name: str | None) -> None:
    """Register SOURCE and create its managed publishing directory."""
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise click.UsageError(f"project directory does not exist: {source}")

    state = load_state()
    projects = project_records(state)
    for existing_slug, project in projects.items():
        if Path(cast(str, project["source"])) == source:
            click.echo(project_dir(existing_slug))
            return

    selected_slug = validate_slug(slug) if slug else slugify(source.name)
    if selected_slug in projects:
        raise click.UsageError(
            f"slug {selected_slug!r} already belongs to {projects[selected_slug]['source']}"
        )

    created_at = datetime.now(UTC).isoformat()
    projects[selected_slug] = {
        "name": name or source.name,
        "source": str(source),
        "created_at": created_at,
        "assets": {},
    }
    project_dir(selected_slug).mkdir(parents=True, exist_ok=False)
    save_state(state)
    click.echo(project_dir(selected_slug))


@cli.command("list")
def list_projects() -> None:
    """List registered projects."""
    state = load_state()
    projects = project_records(state)
    for slug, project in sorted(projects.items()):
        click.echo(
            f"{slug}\t{project['name']}\t{project['source']}\t"
            f"{project_url(slug, state=state)}"
        )


@cli.command()
@click.option("--url", required=True, help="Public base URL for generated links.")
def configure(url: str) -> None:
    """Set host-wide publishing configuration in the shared state file."""
    state = load_state()
    state["url"] = normalize_url(url)
    save_state(state)
    click.echo(state["url"])


@cli.command()
@click.argument("project", required=False)
def path(project: str | None) -> None:
    """Print PROJECT's managed publishing directory."""
    slug, _ = select_project(load_state(), project)
    click.echo(project_dir(slug))


@cli.command()
@click.argument("project", required=False)
def url(project: str | None) -> None:
    """Print PROJECT's published URL."""
    state = load_state()
    slug, _ = select_project(state, project)
    click.echo(project_url(slug, state=state))


@cli.command()
@click.argument("sources", nargs=-1, required=True, type=click.Path(path_type=Path))
@click.option("--project")
@click.option("--to", default=".", help="Relative destination directory.")
@click.option("--key", help="Stable key that owns and replaces one asset.")
@click.option("--force", is_flag=True, help="Replace existing files.")
def add(
    sources: tuple[Path, ...],
    project: str | None,
    to: str,
    key: str | None,
    force: bool,
) -> None:
    """Copy one or more files into a project's publishing directory."""
    state = load_state()
    slug, record = select_project(state, project)
    root = project_dir(slug).resolve()
    destination_dir = asset_path(root, to)
    destination_dir.mkdir(parents=True, exist_ok=True)

    if key is not None:
        key = validate_slug(key)
        if len(sources) != 1:
            raise click.UsageError("--key requires exactly one source")
        source = sources[0].expanduser().resolve()
        if not source.is_file():
            raise click.UsageError(f"asset is not a file: {source}")
        assets = asset_records(record)
        relative = Path(to) / f"{key}{source.suffix}"
        destination = asset_path(root, str(relative))
        claimed = next(
            (
                other_key
                for other_key, other_path in assets.items()
                if other_key != key and other_path == relative.as_posix()
            ),
            None,
        )
        if claimed:
            raise click.UsageError(f"asset path belongs to key {claimed!r}: {relative}")
        previous = assets.get(key)
        if destination.exists() and previous != relative.as_posix() and not force:
            raise click.UsageError(f"unmanaged asset already exists: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if previous and previous != relative.as_posix():
            asset_path(root, previous).unlink(missing_ok=True)
        assets[key] = relative.as_posix()
        save_state(state)
        click.echo(project_url(slug, relative, state))
        return

    for source in sources:
        source = source.expanduser().resolve()
        if not source.is_file():
            raise click.UsageError(f"asset is not a file: {source}")
        destination = asset_path(root, str(Path(to) / source.name))
        if destination.exists() and not force:
            raise click.UsageError(
                f"asset already exists: {destination.relative_to(root)}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        click.echo(project_url(slug, destination.relative_to(root), state))


@cli.command()
@click.argument("project", required=False)
def assets(project: str | None) -> None:
    """List files in PROJECT's publishing directory."""
    state = load_state()
    slug, record = select_project(state, project)
    root = project_dir(slug)
    keys = {path: key for key, path in asset_records(record).items()}
    for asset in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = asset.relative_to(root)
        click.echo(
            f"{relative}\t{asset.stat().st_size}\t"
            f"{project_url(slug, relative, state)}\t{keys.get(str(relative), '')}"
        )


@cli.command()
@click.argument("assets", nargs=-1)
@click.option("--project")
@click.option("--key", help="Remove the asset owned by KEY.")
def remove(assets: tuple[str, ...], project: str | None, key: str | None) -> None:
    """Remove files from a project's publishing directory."""
    if key is not None and assets:
        raise click.UsageError("pass asset paths or --key, not both")
    if key is None and not assets:
        raise click.UsageError("pass at least one asset path or --key")
    state = load_state()
    slug, record = select_project(state, project)
    root = project_dir(slug).resolve()
    managed = asset_records(record)
    if key is not None:
        key = validate_slug(key)
        try:
            assets = (managed.pop(key),)
        except KeyError as error:
            raise click.UsageError(f"unknown asset key: {key}") from error
    for value in assets:
        target = asset_path(root, value)
        if not target.is_file():
            raise click.UsageError(f"asset does not exist or is not a file: {value}")
        target.unlink()
        for managed_key, managed_path in tuple(managed.items()):
            if managed_path == value:
                del managed[managed_key]
        click.echo(value)
    save_state(state)


@cli.command()
@click.argument("project", required=False)
@click.option("--delete-assets", is_flag=True)
def unregister(project: str | None, delete_assets: bool) -> None:
    """Unregister PROJECT, requiring --delete-assets when files remain."""
    state = load_state()
    slug, _ = select_project(state, project)
    directory = project_dir(slug)
    has_assets = any(
        path.is_file() or path.is_symlink() for path in directory.rglob("*")
    )
    if has_assets and not delete_assets:
        raise click.UsageError("publishing directory is not empty; use --delete-assets")
    shutil.rmtree(directory)
    del project_records(state)[slug]
    save_state(state)


if __name__ == "__main__":
    cli()
