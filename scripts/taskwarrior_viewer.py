"""Read-only Taskwarrior viewer with live snapshots."""

import json
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from threading import Condition, Event, Lock, Thread
from typing import Any

import rich_click as click
from flask import Flask, Response, abort, send_from_directory
from waitress import serve
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

UI = Path(__file__).with_name("taskwarrior_ui")
POLL_SECONDS = 15
TASK_OPTIONS = (
    "rc.hooks=off",
    "rc.recurrence=off",
    "rc.gc=off",
    "rc.verbose=nothing",
    "rc.json.array=on",
    "rc.exit.on.missing.db=on",
)


def task(*args: str) -> str:
    return subprocess.run(
        ["task", *TASK_OPTIONS, *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout


class Changes(FileSystemEventHandler):
    def __init__(self, changed: Event) -> None:
        self.changed = changed

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type not in {"created", "modified", "deleted", "moved"}:
            return
        paths = (event.src_path, getattr(event, "dest_path", ""))
        if any(
            Path(str(path)).name in {"taskchampion.sqlite3", "taskchampion.sqlite3-wal"}
            for path in paths
        ):
            self.changed.set()


class Snapshots:
    def __init__(self) -> None:
        self.condition = Condition()
        self.export_lock = Lock()
        self.changed = Event()
        self.stopped = Event()
        self.revision = 0
        self.data: dict[str, Any] = {"tasks": [], "exportedAt": None, "error": ""}
        self.observer = Observer()
        self.worker = Thread(target=self.watch, daemon=True)

    def refresh(self) -> None:
        with self.export_lock:
            try:
                tasks = sorted(json.loads(task("export")), key=lambda t: t["uuid"])
                data = {
                    "tasks": tasks,
                    "exportedAt": datetime.now(UTC).isoformat(),
                    "error": "",
                }
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                data = {**self.data, "error": f"Could not read Taskwarrior: {exc}"}
            with self.condition:
                different = any(data[k] != self.data[k] for k in ("tasks", "error"))
                self.data = data
                if different:
                    self.revision += 1
                    self.condition.notify_all()

    def start(self) -> None:
        directory = Path(task("_get", "rc.data.location").strip()).expanduser()
        self.observer.schedule(Changes(self.changed), str(directory), recursive=False)
        self.observer.start()
        self.refresh()
        self.worker.start()

    def watch(self) -> None:
        while not self.stopped.is_set():
            self.changed.wait(POLL_SECONDS)
            self.changed.clear()
            if self.stopped.wait(0.2):
                break
            self.refresh()

    def close(self) -> None:
        self.stopped.set()
        self.changed.set()
        with self.condition:
            self.condition.notify_all()
        self.observer.stop()
        if self.observer.is_alive():
            self.observer.join()
        if self.worker.is_alive():
            self.worker.join()

    def events(self) -> Iterator[str]:
        revision = -1
        while not self.stopped.is_set():
            with self.condition:
                self.condition.wait_for(
                    lambda: revision != self.revision or self.stopped.is_set(),
                    timeout=POLL_SECONDS,
                )
                if self.stopped.is_set():
                    return
                changed = revision != self.revision
                revision, data = self.revision, self.data
            if changed:
                yield f"id: {revision}\nevent: snapshot\ndata: {json.dumps(data)}\n\n"
            else:
                yield ": keepalive\n\n"


def create(snapshots: Snapshots) -> Flask:
    web = Flask(__name__, static_folder=None)

    @web.get("/api/tasks")
    def tasks() -> Any:
        snapshots.refresh()
        return snapshots.data, {"Cache-Control": "no-store"}

    @web.get("/api/events")
    def events() -> Response:
        return Response(
            snapshots.events(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @web.get("/")
    @web.get("/<path:path>")
    def static(path: str = "") -> Any:
        if path.startswith("api/"):
            abort(404)
        if path and (UI / path).is_file():
            return send_from_directory(UI, path)
        return send_from_directory(UI, "index.html")

    return web


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8066, show_default=True)
def main(host: str, port: int) -> None:
    """Serve a read-only Taskwarrior viewer. Honors TASKRC and TASKDATA."""
    snapshots = Snapshots()
    try:
        snapshots.start()
        click.echo(f"Taskwarrior viewer: http://{host}:{port}")
        serve(create(snapshots), host=host, port=port, threads=16)
    finally:
        snapshots.close()


if __name__ == "__main__":
    main()
