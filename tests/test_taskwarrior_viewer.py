import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import taskwarrior_viewer as viewer


@pytest.fixture
def database(tmp_path, monkeypatch):
    if not shutil.which("task"):
        pytest.skip("Taskwarrior is required")
    config = tmp_path / "taskrc"
    config.write_text("confirmation=off\nnews.version=3.5.0\n")
    monkeypatch.setenv("TASKRC", str(config))
    monkeypatch.setenv("TASKDATA", str(tmp_path / "data"))

    def run(*args, input=None):
        return subprocess.run(
            ["task", "rc.hooks=off", "rc.verbose=nothing", *args],
            input=input,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    run("add", "Read-only fixture 🏡", "project:Documents")
    return run


@pytest.fixture
def live(database):
    snapshots = viewer.Snapshots()
    snapshots.start()
    try:
        yield snapshots, viewer.create(snapshots).test_client()
    finally:
        snapshots.close()


def event_data(chunk):
    if isinstance(chunk, bytes):
        chunk = chunk.decode()
    return json.loads(
        next(line[6:] for line in chunk.splitlines() if line.startswith("data: "))
    )


def test_api_is_read_only_and_ignores_query_commands(live):
    snapshots, http = live
    original = http.get("/api/tasks").json
    assert original["tasks"][0]["description"] == "Read-only fixture 🏡"
    assert original["exportedAt"]
    for route in ("/api/tasks", "/api/events", "/"):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert (
                http.open(route, method=method, json={"command": "delete"}).status_code
                == 405
            )
    result = http.get("/api/tasks?command=delete&filter=all&rc.hooks=on")
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json["tasks"] == original["tasks"]
    assert http.get("/api/missing").status_code == 404
    assert snapshots.data["error"] == ""


def test_cli_changes_reach_sse_without_waiting_for_poll(database, monkeypatch):
    monkeypatch.setattr(viewer, "POLL_SECONDS", 60)
    snapshots = viewer.Snapshots()
    snapshots.start()
    http = viewer.create(snapshots).test_client()
    stream = http.get("/api/events", buffered=False)
    chunks = iter(stream.response)
    try:
        first = event_data(next(chunks))
        uuid = first["tasks"][0]["uuid"]
        revision = snapshots.revision
        database(uuid, "modify", "description:Changed from CLI", "project:Home")
        with snapshots.condition:
            assert snapshots.condition.wait_for(
                lambda: snapshots.revision > revision, timeout=8
            )
        changed = event_data(next(chunks))["tasks"][0]
        assert changed["uuid"] == uuid
        assert changed["description"] == "Changed from CLI"
        assert changed["project"] == "Home"
        revision = snapshots.revision
        database(uuid, "done")
        with snapshots.condition:
            assert snapshots.condition.wait_for(
                lambda: snapshots.revision > revision, timeout=8
            )
        assert event_data(next(chunks))["tasks"][0]["status"] == "completed"
    finally:
        stream.close()
        snapshots.close()


def test_periodic_export_recovers_missed_events(database, monkeypatch):
    monkeypatch.setattr(viewer, "POLL_SECONDS", 0.1)
    monkeypatch.setattr(viewer.Changes, "on_any_event", lambda self, event: None)
    snapshots = viewer.Snapshots()
    snapshots.start()
    try:
        uuid = snapshots.data["tasks"][0]["uuid"]
        database(uuid, "modify", "description:Polling fallback")
        with snapshots.condition:
            assert snapshots.condition.wait_for(
                lambda: snapshots.data["tasks"][0]["description"] == "Polling fallback",
                timeout=5,
            )
    finally:
        snapshots.close()


def test_failed_export_preserves_snapshot_and_recovers(live, monkeypatch):
    snapshots, http = live
    original = http.get("/api/tasks").json
    export = viewer.task

    def fail(*args):
        raise subprocess.TimeoutExpired("task", 10)

    monkeypatch.setattr(viewer, "task", fail)
    stale = http.get("/api/tasks").json
    assert stale["tasks"] == original["tasks"]
    assert stale["exportedAt"] == original["exportedAt"]
    assert stale["error"]
    monkeypatch.setattr(viewer, "task", export)
    assert http.get("/api/tasks").json["error"] == ""


def test_viewing_does_not_generate_recurrences_or_run_hooks(database, tmp_path):
    data = Path(tmp_path / "data")
    hooks = data / "hooks"
    hooks.mkdir(exist_ok=True)
    marker = tmp_path / "hook-ran"
    hook = hooks / "on-launch.fixture"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o755)
    recurring = {
        "uuid": str(uuid4()),
        "description": "Old recurring template",
        "status": "recurring",
        "entry": "20200101T000000Z",
        "due": "20200101T000000Z",
        "recur": "daily",
    }
    database("rc.recurrence=off", "import", "-", input=json.dumps([recurring]))
    before = json.loads(viewer.task("export"))
    assert len(before) == 2
    snapshots = viewer.Snapshots()
    snapshots.refresh()
    viewer.create(snapshots).test_client().get("/api/tasks")
    after = json.loads(viewer.task("export"))
    assert [
        {k: v for k, v in t.items() if k not in {"urgency", "id"}} for t in after
    ] == [{k: v for k, v in t.items() if k not in {"urgency", "id"}} for t in before]
    assert not marker.exists()
