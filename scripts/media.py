"""Mount removable media with terminal polkit authorization."""

import getpass
import json
import os
import select
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from shlex import quote

import click
from click.shell_completion import CompletionItem

UDISKS_TIMEOUT = 120
# Docker group membership already grants host root; a privileged container in
# the host mount namespace avoids the polkit password prompt entirely.
DOCKER_ROOT = [
    *("docker", "run", "--rm", "--privileged", "--pid=host", "alpine"),
    *("nsenter", "-t", "1", "-m", "sh", "-ec"),
]
OWNER_OPTION_FSTYPES = {"vfat", "exfat", "ntfs", "iso9660", "udf"}


def block_devices() -> list[dict]:
    return json.loads(
        subprocess.check_output(
            [
                # Homebrew's lsblk lacks udev metadata for unreadable devices.
                "/usr/bin/lsblk",
                "--json",
                "--tree",
                "--paths",
                "--output",
                "PATH,TYPE,RM,HOTPLUG,FSTYPE",
            ],
            text=True,
        )
    )["blockdevices"]


def media_filesystems(devices: list[dict]):
    for disk in devices:
        if not (
            disk["type"] == "rom"
            or disk["type"] == "disk"
            and (disk["rm"] or disk.get("hotplug"))
        ):
            continue
        for partition in disk.get("children") or [disk]:
            filesystem = partition.get("fstype")
            if (
                filesystem
                and filesystem not in {"swap", "crypto_LUKS", "BitLocker"}
                and not filesystem.endswith("_member")
            ):
                yield disk["path"], partition


def partition_for(devices: list[dict], requested: str | None = None) -> str:
    candidates = [
        partition["path"]
        for disk, partition in media_filesystems(devices)
        if requested is None or requested in {disk, partition["path"]}
    ]
    if not candidates:
        raise ValueError(
            "no mountable filesystem found on removable media"
            + (f": {requested}" if requested else "; connect or insert media")
        )
    if len(candidates) != 1:
        raise ValueError(
            "multiple filesystems found: "
            + ", ".join(candidates)
            + "; select exactly one with --device PATH"
        )
    return candidates[0]


def complete_device(_ctx, _param, incomplete: str) -> list[CompletionItem]:
    return [
        CompletionItem(partition["path"], help=partition["fstype"])
        for _, partition in media_filesystems(block_devices())
        if partition["path"].startswith(incomplete)
    ]


def mountpoint(partition: str) -> Path | None:
    result = subprocess.run(
        ["findmnt", "--json", "--source", partition, "--output", "TARGET"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 1 and not result.stdout.strip():
        return None
    result.check_returncode()
    mounts = json.loads(result.stdout).get("filesystems", [])
    if len(mounts) != 1:
        raise ValueError(f"expected one mountpoint for {partition}")
    return Path(mounts[0]["target"])


def stop_process(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@contextmanager
def terminal_authentication(subject_pid: int):
    """Use this terminal instead of an unattended desktop's polkit agent."""
    if not sys.stdin.isatty():
        yield
        return
    read_fd, write_fd = os.pipe()
    agent = None
    try:
        # The child is waiting on our pipe and cannot exit before registration.
        agent = subprocess.Popen(
            ["pkttyagent", "--process", str(subject_pid), "--notify-fd", str(write_fd)],
            pass_fds=(write_fd,),
        )
        os.close(write_fd)
        write_fd = None
        # pkttyagent closes the inherited descriptor after registration. Wait
        # for that acknowledgement before allowing UDisks to request a prompt.
        ready, _, _ = select.select([read_fd], [], [], 10)
        if not ready or agent.poll() is not None:
            raise OSError("could not start terminal authentication with pkttyagent")
        print(
            "Mount authorization will be requested in this terminal if needed.",
            flush=True,
        )
        yield
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)
        if agent is not None:
            stop_process(agent)


def run_authenticated(command: list[str]):
    # Polkit agents are attached to an exact process, not inherited by its
    # children. Keep the future udisksctl process waiting until its agent is
    # ready, then exec the command without changing its PID or terminal.
    read_fd, write_fd = os.pipe()
    process = None
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import os,sys; fd=int(sys.argv[1]); ready=os.read(fd,1); os.close(fd); "
                "sys.exit(1) if ready!=b'1' else os.execvp(sys.argv[2],sys.argv[2:])",
                str(read_fd),
                *command,
            ],
            pass_fds=(read_fd,),
        )
        os.close(read_fd)
        read_fd = None
        with terminal_authentication(process.pid):
            os.write(write_fd, b"1")
            os.close(write_fd)
            write_fd = None
            result = process.wait(timeout=UDISKS_TIMEOUT)
            if result:
                raise subprocess.CalledProcessError(result, command)
    finally:
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)
        if process is not None:
            stop_process(process)


def polkit_authorized() -> bool:
    return (
        subprocess.run(
            [
                *("pkcheck", "--process", str(os.getpid())),
                *("--action-id", "org.freedesktop.udisks2.filesystem-mount"),
            ],
            capture_output=True,
        ).returncode
        == 0
    )


def docker_root() -> bool:
    daemon = subprocess.run(
        ["docker", "info", "--format", "{{.SecurityOptions}}"],
        capture_output=True,
        text=True,
    )
    return daemon.returncode == 0 and "rootless" not in daemon.stdout


def root_script(action: str, partition: str) -> str:
    if action == "unmount":
        return (
            f"umount {quote(partition)}; rmdir {quote(str(mountpoint(partition)))} || :"
        )
    info = json.loads(
        subprocess.check_output(
            ["/usr/bin/lsblk", "--json", "--output", "FSTYPE,LABEL,UUID", partition],
            text=True,
        )
    )["blockdevices"][0]
    target = quote(f"/run/media/{getpass.getuser()}/{info['label'] or info['uuid']}")
    options = "nosuid,nodev"
    if info["fstype"] in OWNER_OPTION_FSTYPES:
        options += f",uid={os.getuid()},gid={os.getgid()}"
    return f"mkdir -p {target} && mount -o {options} {quote(partition)} {target}"


def udisks(action: str, partition: str):
    as_root = not polkit_authorized() and docker_root()
    print(
        f"{'Mounting' if action == 'mount' else 'Unmounting'} {partition}"
        f"{' as root via docker' if as_root else ''}...",
        flush=True,
    )
    command = ["udisksctl", action, "--block-device", partition]
    try:
        if as_root:
            subprocess.run(
                [*DOCKER_ROOT, root_script(action, partition)],
                check=True,
                timeout=UDISKS_TIMEOUT,
            )
        elif sys.stdin.isatty():
            run_authenticated(command)
        else:
            command.append("--no-user-interaction")
            subprocess.run(command, check=True, timeout=UDISKS_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise OSError(
            f"{action} timed out after {UDISKS_TIMEOUT}s; "
            "check mount state before removing the media"
        ) from error


def interrupted(signum, _frame):
    raise SystemExit(128 + signum)


@click.command()
@click.option(
    "--device",
    type=click.Path(
        exists=True, readable=False, dir_okay=False, path_type=Path, resolve_path=True
    ),
    shell_complete=complete_device,
    help="Media device (default: the only removable filesystem).",
)
@click.pass_context
def main(ctx: click.Context, device: Path | None):
    """Mount or unmount removable media with authorization in this terminal."""
    action = "unmount" if ctx.info_name == "umount-media" else "mount"
    signal.signal(signal.SIGTERM, interrupted)
    try:
        partition = partition_for(
            block_devices(), str(device) if device is not None else None
        )
        if not Path(partition).is_block_device():
            raise ValueError(f"not a block device: {partition}")
        target = mountpoint(partition)
        if (action == "mount") != (target is not None):
            udisks(action, partition)
        elif target is not None:
            click.echo(f"{partition} is already mounted at {target}.")
        else:
            click.echo(f"{partition} is already unmounted.")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error
