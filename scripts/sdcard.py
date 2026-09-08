"""Mount removable FAT/exFAT filesystems with terminal polkit authorization."""

import json
import os
import select
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import click

UDISKS_TIMEOUT = 120


def partition_for(devices: list[dict], requested: str | None = None) -> str:
    if requested is None:
        candidates = [
            partition["path"]
            for disk in devices
            if disk["type"] == "disk" and disk["rm"]
            for partition in disk.get("children") or [disk]
            if partition.get("fstype") in {"vfat", "exfat"}
        ]
        if not candidates:
            raise ValueError(
                "no removable FAT/exFAT partition found; connect the SD card"
            )
        if len(candidates) != 1:
            raise ValueError(
                "multiple removable FAT/exFAT partitions found: "
                + ", ".join(candidates)
                + "; select one with --device PATH"
            )
        return candidates[0]
    for disk in devices:
        children = disk.get("children", [])
        matches = [p for p in [disk, *children] if p["path"] == requested]
        if not matches:
            continue
        if disk["type"] != "disk" or not disk["rm"]:
            raise ValueError("target must belong to a removable disk")
        selected = matches[0]
        candidates = children if selected is disk and children else [selected]
        candidates = [p for p in candidates if p.get("fstype") in {"vfat", "exfat"}]
        if len(candidates) != 1:
            raise ValueError("select exactly one FAT/exFAT partition with --device")
        return candidates[0]["path"]
    raise ValueError(f"device is absent or is not a disk/partition: {requested}")


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


def udisks(action: str, partition: str):
    command = ["udisksctl", action, "--block-device", partition]
    if not sys.stdin.isatty():
        command.append("--no-user-interaction")
    print(
        f"{'Mounting' if action == 'mount' else 'Unmounting'} {partition}...",
        flush=True,
    )
    try:
        if sys.stdin.isatty():
            run_authenticated(command)
        else:
            subprocess.run(command, check=True, timeout=UDISKS_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise OSError(
            f"{action} timed out after {UDISKS_TIMEOUT}s; "
            "check mount state before removing the card"
        ) from error


def interrupted(signum, _frame):
    raise SystemExit(128 + signum)


@click.command()
@click.option(
    "--device",
    type=click.Path(exists=True, path_type=Path, resolve_path=True),
    help="Disk or partition (default: the only removable FAT/exFAT filesystem).",
)
@click.pass_context
def main(ctx: click.Context, device: Path | None):
    """Mount or unmount an SD card with authorization in this terminal."""
    action = "unmount" if ctx.info_name == "umount-sd" else "mount"
    signal.signal(signal.SIGTERM, interrupted)
    try:
        inventory = json.loads(
            subprocess.check_output(
                [
                    "lsblk",
                    "--json",
                    "--tree",
                    "--paths",
                    "--output",
                    "PATH,TYPE,RM,FSTYPE",
                ],
                text=True,
            )
        )
        partition = partition_for(
            inventory["blockdevices"], str(device) if device is not None else None
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
