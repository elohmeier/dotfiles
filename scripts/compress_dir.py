from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import rich_click as click
from rich.console import Console

FD_BIN = shutil.which("fd")
if not FD_BIN:
    raise SystemExit("fd is required for compress-dir")


def fd_command(include_dirs: bool) -> list[str]:
    cmd = [
        FD_BIN,
        "--hidden",
        "--strip-cwd-prefix",
        "--exclude",
        ".git",
        "--exclude",
        ".svn",
        "--exclude",
        ".hg",
        "--print0",
    ]
    return (
        cmd
        + (
            ["--type", "directory"]
            if include_dirs
            else ["--type", "file", "--type", "symlink"]
        )
        + ["."]
    )


console = Console(stderr=True)


@click.command(help="Create a zstd-compressed tar archive honoring VCS ignore rules.")
@click.argument(
    "target", default=".", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Archive path (default: <target>.tar.zst).",
)
@click.option(
    "-l",
    "--level",
    default=19,
    show_default=True,
    type=int,
    help="zstd compression level.",
)
@click.option(
    "-t",
    "--threads",
    type=int,
    help="zstd worker threads (default: env ZSTD_NBTHREADS or 1).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Print compression progress.",
)
def main(
    target: Path, output: Path | None, level: int, threads: int | None, verbose: bool
) -> None:
    target = target.expanduser().resolve()
    out_path = (
        (output if output else Path.cwd() / f"{target.name}.tar.zst")
        .expanduser()
        .resolve()
    )

    tar_proc = subprocess.Popen(
        ["tar", "-C", str(target), "--null", "--no-recursion", "-T", "-", "-cf", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert tar_proc.stdin is not None
    assert tar_proc.stdout is not None

    env = os.environ.copy()
    env["ZSTD_NBTHREADS"] = str(threads) if threads else env.get("ZSTD_NBTHREADS", "1")
    if verbose:
        console.log(
            f"Compressing {target} -> {out_path} (level={level}, threads={env['ZSTD_NBTHREADS']})"
        )

    zstd_proc = subprocess.Popen(
        ["zstd", f"-{level}", "--quiet", "-o", str(out_path)],
        stdin=tar_proc.stdout,
        env=env,
    )
    tar_proc.stdout.close()

    for include_dirs in (False, True):
        subprocess.run(
            fd_command(include_dirs),
            cwd=target,
            stdout=tar_proc.stdin,
            check=True,
        )

    tar_proc.stdin.close()
    if tar_proc.wait():
        zstd_proc.wait()
        raise SystemExit(1)
    if zstd_proc.wait():
        raise SystemExit(1)
    if verbose:
        console.log(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
