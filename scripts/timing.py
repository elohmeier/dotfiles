"""Timers and process completion helpers."""

import os
import re
import shutil
import subprocess
import sys
import time

import rich_click as click


def notify(title: str, message: str) -> None:
    click.echo(f"\a{title}: {message}", err=True)
    if command := shutil.which("agent-pushover-notify"):
        subprocess.run([command, title, message], check=True)
    elif sys.platform == "darwin":
        subprocess.run(
            [
                "osascript",
                "-e",
                "on run argv\n"
                "display notification (item 2 of argv) with title (item 1 of argv)\n"
                "end run",
                title,
                message,
            ],
            check=True,
        )
    elif command := shutil.which("notify-send"):
        subprocess.run([command, title, message], check=True)


def wait_pid(pid: int) -> None:
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.5)


@click.command()
@click.argument("duration")
def timer(duration: str) -> None:
    """Wait for DURATION (e.g. 30s, 10m, 1.5h), then ring and send a notification."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smh]?)", duration)
    if not match:
        raise click.BadParameter("Use seconds, or a number followed by s, m, or h.")
    seconds = float(match[1]) * {"": 1, "s": 1, "m": 60, "h": 3600}[match[2]]
    time.sleep(seconds)
    notify("Timer", f"{duration} timer complete")


@click.command()
@click.argument("pid", type=click.IntRange(min=1))
@click.option(
    "--notify", "send_notification", is_flag=True, help="Notify when PID exits."
)
def waitfor(pid: int, send_notification: bool) -> None:
    """Wait for PID to exit, keeping the system awake when supported.

    This cannot recover the process's exit status.
    """
    if command := shutil.which("caffeinate"):
        subprocess.run([command, "-i", "-w", str(pid)], check=True)
    elif command := shutil.which("systemd-inhibit"):
        with subprocess.Popen(
            [
                command,
                "--what=idle:sleep",
                f"--why=Waiting for PID {pid}",
                "cat",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        ):
            wait_pid(pid)
    else:
        wait_pid(pid)
    if send_notification:
        notify("Process", f"PID {pid} exited")
