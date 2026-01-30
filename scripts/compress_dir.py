from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import rich_click as click
from rich.console import Console


def get_dir_size(path: Path) -> int:
    """Return total size of directory in bytes."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


_fd_bin = shutil.which("fd")
if not _fd_bin:
    raise SystemExit("fd is required for compress-dir")
FD_BIN = _fd_bin


def fd_command(include_dirs: bool, exclude_git: bool = True) -> list[str]:
    cmd = [
        FD_BIN,
        "--hidden",
        "--strip-cwd-prefix",
        "--exclude",
        ".svn",
        "--exclude",
        ".hg",
        "--print0",
    ]
    if exclude_git:
        cmd.extend(["--exclude", ".git"])
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
@click.option(
    "--no-git",
    is_flag=True,
    help="Exclude .git directory entirely.",
)
@click.option(
    "--git-full-threshold",
    default=500,
    show_default=True,
    type=int,
    help="Include full .git if smaller than this (KB). 0=always shallow.",
)
def main(
    target: Path,
    output: Path | None,
    level: int,
    threads: int | None,
    verbose: bool,
    no_git: bool,
    git_full_threshold: int,
) -> None:
    target = target.expanduser().resolve()
    out_path = (
        (output if output else Path.cwd() / f"{target.name}.tar.zst")
        .expanduser()
        .resolve()
    )

    git_dir = target / ".git"
    has_git = git_dir.is_dir()
    include_git = has_git and not no_git

    # Determine if we need a shallow clone
    git_source: Path | None = None
    use_shallow = False
    if include_git:
        git_size_kb = get_dir_size(git_dir) // 1024
        use_shallow = git_full_threshold == 0 or git_size_kb >= git_full_threshold
        if not use_shallow:
            git_source = target

    env = os.environ.copy()
    env["ZSTD_NBTHREADS"] = str(threads) if threads else env.get("ZSTD_NBTHREADS", "1")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        tar_path = tmppath / "archive.tar"

        # Create shallow clone if needed
        if include_git and use_shallow:
            clone_dir = tmppath / "shallow"
            if verbose:
                console.log(f"Creating shallow clone of .git ({git_size_kb} KB)")
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    f"file://{target}",
                    str(clone_dir),
                ],
                check=True,
                capture_output=True,
            )
            git_source = clone_dir

        if verbose:
            msg = f"Compressing {target} -> {out_path} (level={level}, threads={env['ZSTD_NBTHREADS']})"
            if include_git:
                msg += f", .git={'shallow' if use_shallow else 'full'}"
            console.log(msg)

        # Pass 1: create tar from fd (always excluding .git, we add it separately)
        tar_proc = subprocess.Popen(
            [
                "tar",
                "-C",
                str(target),
                "--null",
                "--no-recursion",
                "-T",
                "-",
                "-cf",
                str(tar_path),
            ],
            stdin=subprocess.PIPE,
        )
        assert tar_proc.stdin is not None

        for include_dirs in (False, True):
            subprocess.run(
                fd_command(include_dirs, exclude_git=True),
                cwd=target,
                stdout=tar_proc.stdin,
                check=True,
            )

        tar_proc.stdin.close()
        if tar_proc.wait():
            raise SystemExit(1)

        # Pass 2: append .git if needed
        if include_git and git_source:
            subprocess.run(
                ["tar", "-C", str(git_source), "-rf", str(tar_path), ".git"],
                check=True,
            )

        # Compress
        subprocess.run(
            [
                "zstd",
                f"-{level}",
                "--quiet",
                "--rm",
                "-o",
                str(out_path),
                str(tar_path),
            ],
            env=env,
            check=True,
        )

    if verbose:
        console.log(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
