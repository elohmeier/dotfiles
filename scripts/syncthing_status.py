"""Show outbound Syncthing progress and ETA."""

import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import click
import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text


@dataclass
class Transfer:
    folder: str
    device: str
    device_id: str
    completion: float
    remaining: int
    items: int
    paused: bool
    connected: bool
    rate: float = 0
    eta: float | None = None


def api_client() -> httpx.Client:
    paths = subprocess.check_output(["syncthing", "paths"], text=True)
    config = Path(paths.split("Configuration file:\n\t", 1)[1].splitlines()[0])
    gui = ET.parse(config).getroot().find("gui")
    assert gui is not None
    address = gui.findtext("address", "127.0.0.1:8384")
    address = address.replace("0.0.0.0", "127.0.0.1").replace("[::]", "[::1]")
    scheme = "https" if gui.get("tls") == "true" else "http"
    return httpx.Client(
        base_url=f"{scheme}://{address}",
        headers={"X-API-Key": gui.findtext("apikey", "")},
        timeout=5,
        verify=False,
    )


def snapshot(client: httpx.Client) -> tuple[list[Transfer], dict[str, int]]:
    config = client.get("/rest/config").raise_for_status().json()
    system = client.get("/rest/system/status").raise_for_status().json()
    connections = (
        client.get("/rest/system/connections").raise_for_status().json()["connections"]
    )
    devices = {device["deviceID"]: device for device in config["devices"]}
    transfers = []

    for folder in config["folders"]:
        for shared in folder["devices"]:
            device_id = shared["deviceID"]
            if device_id == system["myID"]:
                continue
            completion = (
                client.get(
                    "/rest/db/completion",
                    params={"folder": folder["id"], "device": device_id},
                )
                .raise_for_status()
                .json()
            )
            device = devices[device_id]
            connection = connections.get(device_id, {})
            transfers.append(
                Transfer(
                    folder=folder.get("label") or folder["id"],
                    device=device.get("name") or device_id[:7],
                    device_id=device_id,
                    completion=completion["completion"],
                    remaining=completion["needBytes"],
                    items=completion["needItems"] + completion["needDeletes"],
                    paused=folder["paused"] or device["paused"],
                    connected=connection.get("connected", False),
                )
            )

    counters = {
        device_id: connection["outBytesTotal"]
        for device_id, connection in connections.items()
    }
    return transfers, counters


def measure(
    client: httpx.Client, previous: dict[str, int], elapsed: float
) -> tuple[list[Transfer], dict[str, int]]:
    transfers, counters = snapshot(client)
    rates = {
        device_id: max(0, total - previous.get(device_id, total)) / elapsed
        for device_id, total in counters.items()
    }
    remaining = {}
    for transfer in transfers:
        remaining[transfer.device_id] = (
            remaining.get(transfer.device_id, 0) + transfer.remaining
        )
    for transfer in transfers:
        transfer.rate = rates.get(transfer.device_id, 0)
        if transfer.rate and transfer.remaining:
            transfer.eta = remaining[transfer.device_id] / transfer.rate
    return transfers, counters


def human_bytes(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def state(transfer: Transfer) -> tuple[str, str]:
    if transfer.paused:
        return "paused", "yellow"
    if transfer.completion >= 100 and transfer.items == 0:
        return "synced", "green"
    if not transfer.connected:
        return "offline", "red"
    if transfer.rate >= 1024:
        return "transferring", "cyan"
    return "waiting", "yellow"


def render(transfers: list[Transfer], show_all: bool) -> Table | Group:
    visible = [t for t in transfers if show_all or state(t)[0] != "synced"]
    if not visible:
        return Group(Text("✓ No outbound work pending", style="green"))

    table = Table(box=None, pad_edge=False)
    table.add_column("STATE")
    table.add_column("FOLDER")
    table.add_column("DESTINATION")
    table.add_column("DONE", justify="right")
    table.add_column("LEFT", justify="right")
    table.add_column("OUT", justify="right")
    table.add_column("ETA", justify="right")
    for transfer in visible:
        label, color = state(transfer)
        table.add_row(
            Text(label, style=color),
            transfer.folder,
            transfer.device,
            f"{transfer.completion:6.2f}%",
            human_bytes(transfer.remaining),
            f"{human_bytes(transfer.rate)}/s" if transfer.rate else "—",
            duration(transfer.eta),
        )
    return table


@click.command()
@click.option("--watch", "watching", "-w", is_flag=True, help="Refresh until stopped.")
@click.option("--all", "show_all", "-a", is_flag=True, help="Include synced folders.")
@click.option(
    "--interval", "-i", default=2.0, show_default=True, type=click.FloatRange(min=0.2)
)
def main(watching: bool, show_all: bool, interval: float) -> None:
    """Show outbound folder sync status, transfer rate, and ETA."""
    console = Console()
    with api_client() as client:
        _, counters = snapshot(client)
        started = time.monotonic()
        time.sleep(interval)
        transfers, counters = measure(client, counters, time.monotonic() - started)
        if not watching:
            console.print(render(transfers, show_all))
            return

        try:
            with Live(
                render(transfers, show_all), console=console, refresh_per_second=4
            ) as live:
                while True:
                    started = time.monotonic()
                    time.sleep(interval)
                    transfers, counters = measure(
                        client, counters, time.monotonic() - started
                    )
                    live.update(render(transfers, show_all))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
