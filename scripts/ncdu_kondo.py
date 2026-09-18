# /// script
# requires-python = ">=3.14"
# dependencies = ["click"]
# ///
"""Discover project artifacts and browse their full contents in ncdu."""

import fnmatch
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections import deque
from collections.abc import Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from itertools import batched
from pathlib import Path
from typing import TextIO

import click

# Ambiguous names such as build, target and vendor require a project marker.
RULES = {
    "package.json": ("node_modules", ".angular", ".next", ".nuxt", ".svelte-kit"),
    "Cargo.toml": ("target", ".xwin-cache"),
    "composer.json": ("vendor",),
    "pom.xml": ("target",),
    "build.gradle": ("build", ".gradle"),
    "build.gradle.kts": ("build", ".gradle"),
    "build.sbt": ("target", "project/target"),
    "CMakeLists.txt": ("build", "cmake-build-debug", "cmake-build-release"),
    "mix.exs": ("_build", ".elixir_ls", ".elixir-tools", ".lexical"),
    "Package.swift": (".build",),
    "build.zig": ("zig-cache", ".zig-cache", "zig-out"),
    "pubspec.yaml": ("build", ".dart_tool"),
    "stack.yaml": (".stack-work",),
    "cabal.project": ("dist-newstyle",),
    "project.godot": (".godot",),
    "*.csproj": ("bin", "obj"),
    "*.fsproj": ("bin", "obj"),
    "turbo.json": (".turbo",),
    ".terraform.lock.hcl": (".terraform",),
    "Podfile": ("Pods",),
}
PYTHON_CACHES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "__pypackages__",
    ".ipynb_checkpoints",
}
VCS = {".git", ".hg", ".svn"}
type Tree = dict[str, Tree | None]
type Part = str | tuple[str, str]
ENCODE = json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).encode


def discover(root: Path, excluded: set[str]) -> list[Path]:
    """Read directory listings, pruning artifacts before walking their contents."""
    candidates: list[Path] = []
    expected: set[Path] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            children = list(entries)
        files = {e.name for e in children if e.is_file(follow_symlinks=False)}
        for marker, artifacts in RULES.items():
            if marker in files or (
                "*" in marker
                and any(fnmatch.fnmatchcase(name, marker) for name in files)
            ):
                expected.update(directory / name for name in artifacts)
        for entry in children:
            if entry.name in excluded or not entry.is_dir(follow_symlinks=False):
                continue
            path = Path(entry.path)
            virtualenv = (
                entry.name in {".venv", "venv"} and (path / "pyvenv.cfg").is_file()
            )
            if path in expected or entry.name in PYTHON_CACHES or virtualenv:
                candidates.append(path)
            else:
                pending.append(path)
    return sorted(candidates)


def dump(value: object, output: TextIO) -> None:
    output.write(ENCODE(value))


def metadata(name: str, info: os.stat_result) -> dict[str, str | int]:
    metadata = {
        "name": name,
        "asize": info.st_size,
        "dsize": info.st_blocks * 512,
        "dev": info.st_dev,
        "mtime": max(0, int(info.st_mtime)),
    }
    if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
        metadata.update(ino=info.st_ino, nlink=info.st_nlink)
    elif not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
        metadata["notreg"] = True
    return metadata


def write_artifact(path: str, name: str, info: os.stat_result, output: TextIO) -> None:
    """Stream each entry once; symlinks are recorded but never followed."""
    is_dir = stat.S_ISDIR(info.st_mode)
    if is_dir:
        output.write("[")
    dump(metadata(name, info), output)
    if is_dir:
        with os.scandir(path) as entries:
            for entry in entries:
                output.write(",")
                write_artifact(
                    entry.path, entry.name, entry.stat(follow_symlinks=False), output
                )
        output.write("]")


def artifact_parts(path: str, name: str, depth: int) -> Iterator[Part]:
    """Expose cache subtrees as independent work, retaining their JSON nesting."""
    if depth == 0:
        yield path, name
        return
    info = os.lstat(path)
    header = ENCODE(metadata(name, info))
    if not stat.S_ISDIR(info.st_mode):
        yield header
        return
    yield "[" + header
    with os.scandir(path) as entries:
        for entry in entries:
            yield ","
            yield from artifact_parts(entry.path, entry.name, depth - 1)
    yield "]"


def tree_parts(
    path: Path, tree: Tree, depth: int, *, root: bool = False
) -> Iterator[Part]:
    # These ancestors provide navigation only; their own sizes are not cache usage.
    yield "[" + ENCODE({"name": str(path) if root else path.name})
    for name, branch in tree.items():
        child = path / name
        yield ","
        if branch is None:
            yield from artifact_parts(str(child), name, depth)
        else:
            yield from tree_parts(child, branch, depth)
    yield "]"


def write_parts(parts: Iterable[Part], output: TextIO) -> None:
    for part in parts:
        if isinstance(part, str):
            output.write(part)
        else:
            path, name = part
            write_artifact(path, name, os.lstat(path), output)


def spool(parts: tuple[Part, ...], destination: Path) -> Path:
    with destination.open("w", encoding="utf-8", errors="surrogateescape") as output:
        write_parts(parts, output)
    return destination


def assemble(future: Future[Path], output: TextIO) -> None:
    path = future.result()
    with path.open(encoding="utf-8", errors="surrogateescape", newline="") as source:
        shutil.copyfileobj(source, output)
    path.unlink()


def parallel_write(parts: Iterable[Part], output: TextIO, jobs: int) -> None:
    # At most two batches per worker are queued or spooled. Workers never wait
    # for other workers or write to the shared output. Errors abort the export.
    with tempfile.TemporaryDirectory(prefix="ncdu-kondo-parts-") as temporary:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            pending: deque[Future[Path]] = deque()
            for index, batch in enumerate(batched(parts, 8)):
                if len(pending) == jobs * 2:
                    assemble(pending.popleft(), output)
                pending.append(pool.submit(spool, batch, Path(temporary) / str(index)))
            for future in pending:
                assemble(future, output)


def export(root: Path, candidates: list[Path], output: TextIO, jobs: int = 4) -> None:
    tree: Tree = {}
    for candidate in candidates:
        branch = tree
        parts = candidate.relative_to(root).parts
        for part in parts[:-1]:
            child = branch.setdefault(part, {})
            assert child is not None
            branch = child
        branch[parts[-1]] = None
    output.write("[1,2,")
    dump({"progname": "ncdu-kondo", "timestamp": int(time.time())}, output)
    output.write(",")
    parts = tree_parts(root, tree, 1 if jobs > 1 else 0, root=True)
    if jobs == 1:
        write_parts(parts, output)
    else:
        parallel_write(parts, output, jobs)
    output.write("]\n")


@click.command(name="ncdu-kondo")
@click.argument(
    "directory",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--export",
    "destination",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write ncdu JSON instead of opening ncdu (does not require ncdu).",
)
@click.option(
    "--exclude",
    multiple=True,
    metavar="NAME",
    help="Skip directories with this exact name during discovery; repeatable.",
)
@click.option(
    "--jobs",
    "-j",
    type=click.IntRange(1),
    default=4,
    show_default=True,
    help="Concurrent subtree scans; use 1 for sequential scanning.",
)
@click.option(
    "--timings",
    is_flag=True,
    help="Report stage times, including an extra read-only ncdu import when available.",
)
def cli(
    directory: Path,
    destination: Path | None,
    exclude: tuple[str, ...],
    jobs: int,
    timings: bool,
) -> None:
    """Find project caches under DIRECTORY and inspect/delete them manually in ncdu.

    Shows all recognized artifacts, including those in active projects. Symlink
    directories and version-control metadata are skipped during discovery.
    Requires ncdu 2.x for interactive use. Press d in ncdu to delete a selection.
    """
    if destination is None and shutil.which("ncdu") is None:
        raise click.ClickException("ncdu is required; install it or use --export.")
    root = directory.resolve()
    try:
        start = time.perf_counter()
        click.echo(f"Finding project caches under {root}...", err=True)
        candidates = discover(root, VCS | set(exclude))
        click.echo(f"Found {len(candidates)} cache directories.", err=True)
        if timings:
            click.echo(f"Discovery: {time.perf_counter() - start:.3f}s", err=True)
        if not candidates and destination is None:
            return
        click.echo(f"Measuring cache contents ({jobs} workers)...", err=True)
        with tempfile.TemporaryDirectory(prefix="ncdu-kondo-") as temporary:
            scan = Path(temporary) / "scan.json"
            start = time.perf_counter()
            with scan.open("w", encoding="utf-8", errors="surrogateescape") as output:
                export(root, candidates, output, jobs)
            if timings:
                click.echo(f"Scan/export: {time.perf_counter() - start:.3f}s", err=True)
                if shutil.which("ncdu"):
                    start = time.perf_counter()
                    subprocess.run(
                        [
                            "ncdu",
                            "--ignore-config",
                            "-0",
                            "-e",
                            "-f",
                            str(scan),
                            "--quit-after-scan",
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    click.echo(
                        f"ncdu import (extra pass): {time.perf_counter() - start:.3f}s",
                        err=True,
                    )
            if destination is not None:
                shutil.copyfile(scan, destination)
                click.echo(f"Exported to {destination}", err=True)
            else:
                result = subprocess.run(
                    [
                        "ncdu",
                        "--ignore-config",
                        "-e",
                        "-f",
                        str(scan),
                        "--enable-delete",
                        "--confirm-delete",
                        "--disable-refresh",
                        "--disable-shell",
                    ],
                    check=False,
                )
                if result.returncode:
                    raise click.ClickException(f"ncdu exited with {result.returncode}.")
    except (OSError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error


def main() -> None:
    """Keep the free-threaded runtime isolated from the other packaged CLIs."""
    if getattr(sys, "_is_gil_enabled", lambda: True)():
        # A free-threaded build with an explicitly enabled GIL must not loop.
        if "free-threading build" in sys.version:
            raise SystemExit(
                "ncdu-kondo: The GIL is enabled; unset PYTHON_GIL or run with -X gil=0."
            )
        os.execvp(
            "uv",
            ["uv", "run", "--python", "3.14t", "--script", __file__, *sys.argv[1:]],
        )
    cli(prog_name="ncdu-kondo")


if __name__ == "__main__":
    main()
