"""Chrome profile manager CLI and upload server."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import click
from flask import Flask, request


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB max upload size

_profile_name: str | None = None
_launch_chrome: bool = True


@app.route("/")
def index() -> str:
    return f"""
    <h3>Profile: {_profile_name}</h3>
    <form method="POST" action="/upload" enctype="multipart/form-data">
        <input type="file" name="zipfile" accept=".zip" required>
        <input type="submit" value="Upload">
    </form>
    """


@app.route("/upload", methods=["POST"])
def upload() -> str:
    if "zipfile" not in request.files:
        return "No file uploaded"

    file = request.files["zipfile"]
    if file.filename == "":
        return "No file selected"

    if not file.filename.endswith(".zip"):
        return "Only ZIP files allowed"

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
        file.save(tmp_file.name)
        tmp_path = Path(tmp_file.name)

    try:
        result = replace_profile(
            tmp_path, _profile_name or "", launch=_launch_chrome, verbose=False
        )

        def shutdown_server() -> None:
            time.sleep(1)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=shutdown_server, daemon=True).start()
        return result
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_zip_into_profile(
    zip_path: Path, profile_path: Path, verbose: bool
) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        if archive.testzip() is not None:
            raise zipfile.BadZipFile("Corrupted ZIP file")

        members = archive.namelist()
        if verbose:
            click.echo(f"✓ Verified ZIP file ({len(members)} files/folders)")
        if verbose:
            click.echo(f"→ Extracting {len(members)} items to profile...")

        normalized = [name.replace("\\", "/") for name in members]
        if normalized and normalized[0] and "/" in normalized[0]:
            first_dir = normalized[0].split("/")[0]
            if all(
                name.startswith(first_dir + "/") or name == first_dir + "/"
                for name in normalized
                if name
            ):
                if verbose:
                    click.echo(f"→ Detected nested structure: '{first_dir}'")
                for member in members:
                    normalized_member = member.replace("\\", "/")
                    if normalized_member in {first_dir, first_dir + "/"}:
                        continue
                    if normalized_member.startswith(first_dir + "/"):
                        target_name = normalized_member[len(first_dir) + 1 :]
                    else:
                        continue
                    _extract_member(archive, member, profile_path / target_name)
                return

        for member in members:
            normalized_member = member.replace("\\", "/")
            _extract_member(archive, member, profile_path / normalized_member)


def _extract_member(archive: zipfile.ZipFile, member: str, target: Path) -> None:
    if member.endswith(("/", "\\")):
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, open(target, "wb") as dest:
            shutil.copyfileobj(source, dest)


def replace_profile(
    zip_path: Path | str, profile: str, *, launch: bool = True, verbose: bool = True
) -> str:
    zip_path = Path(zip_path)
    profile_path = (
        Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / profile
    )

    if verbose:
        click.echo(f"→ Target profile path: {profile_path}")

    if profile_path.exists():
        if verbose:
            click.echo(f"→ Removing existing profile '{profile}'...")
        shutil.rmtree(profile_path)

    profile_path.mkdir(parents=True, exist_ok=True)
    _extract_zip_into_profile(zip_path, profile_path, verbose)

    if verbose:
        click.echo(f"✓ Profile '{profile}' replaced successfully")

    if launch:
        chrome_path = Path(
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
        if verbose:
            click.echo(f"→ Launching Chrome with profile '{profile}'...")
        subprocess.Popen([str(chrome_path), f"--profile-directory={profile}"])

    return "Success"


@click.group()
def cli() -> None:
    """Chrome profile manager."""


@cli.command()
@click.argument("zip_file", type=click.Path(exists=True, path_type=Path))
@click.option("--profile", default="chrome-profile-manager", help="Chrome profile name")
@click.option(
    "--no-launch", is_flag=True, help="Do not launch Chrome after replacing profile"
)
def local(zip_file: Path, profile: str, no_launch: bool) -> None:
    try:
        result = replace_profile(zip_file, profile, launch=not no_launch, verbose=True)
        click.echo(result)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"✗ Error: {exc}", err=True)


@cli.command()
@click.option("--profile", default="chrome-profile-manager", help="Chrome profile name")
@click.option("--port", default=18080, help="Port to run server on")
@click.option(
    "--no-launch", is_flag=True, help="Do not launch Chrome after replacing profile"
)
def server(profile: str, port: int, no_launch: bool) -> None:
    from waitress import serve

    global _profile_name, _launch_chrome  # noqa: PLW0603

    _profile_name = profile
    _launch_chrome = not no_launch

    click.echo(f"Server running at http://0.0.0.0:{port}")
    click.echo(f"Profile: {profile}")
    if no_launch:
        click.echo("Chrome will NOT be launched after upload")

    serve(app, host="0.0.0.0", port=port, channel_timeout=300)


def main() -> None:
    cli.main()


if __name__ == "__main__":
    main()
