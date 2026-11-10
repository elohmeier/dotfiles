import json
import os

import pytest

from scripts import agent_session as app
from scripts import agent_session_web as web


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(web, "refreshed", 0.0)
    store = app.Store("claude:host", tmp_path / "claude")
    monkeypatch.setattr(app, "stores", lambda: [store])
    cwd = tmp_path.resolve()
    session = app.write_claude(
        store,
        cwd,
        "Fixture",
        [
            app.message("user", "find the needle"),
            app.message(
                "assistant",
                [
                    {"type": "text", "text": "Looking."},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "ls"},
                    },
                ],
            ),
            app.message(
                "user",
                [{"type": "tool_result", "tool_use_id": "t1", "content": "needle.txt"}],
            ),
            app.message("assistant", "Found it."),
        ],
    )
    # A later record from a subdirectory must not move where the session resumes.
    with session.path.open("a") as file:
        file.write(json.dumps({"type": "progress", "cwd": str(cwd / "sub")}) + "\n")
    return web.create().test_client(), session, cwd


def test_workspaces_and_sessions(client):
    http, session, cwd = client
    [workspace] = http.get("/api/workspaces").json
    assert workspace["key"] == str(cwd)
    assert workspace["latest"]["ref"] == session.ref
    assert workspace["latest"]["resume"].startswith(f"cd -- {cwd} && ")
    rows = http.get("/api/sessions", query_string={"workspace": str(cwd)}).json
    assert [r["ref"] for r in rows] == [session.ref]
    [match] = http.get("/api/sessions", query_string={"q": "needle"}).json
    assert "\x02needle\x03" in match["snippet"]
    assert http.get("/api/sessions", query_string={"agent": "pi"}).json == []


def test_session_pairs_tool_results_and_merges_assistant_turns(client):
    http, session, _ = client
    detail = http.get("/api/session", query_string={"ref": session.ref}).json
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["blocks"] == [
        {"type": "text", "text": "Looking."},
        {
            "type": "tool",
            "name": "Bash",
            "input": '{"command": "ls"}',
            "output": "needle.txt",
            "error": False,
        },
        {"type": "text", "text": "Found it."},
    ]
    assert http.get("/api/session", query_string={"ref": "missing"}).status_code == 404


def test_clip_keeps_both_ends():
    text = "a" * web.CLIP + "z"
    clipped = web.clip(text)
    assert clipped.startswith("a") and clipped.endswith("z")
    assert "1 characters omitted" in clipped


def test_search_sorts_by_recency(client, monkeypatch):
    http, session, cwd = client
    newer = app.write_claude(
        app.stores()[0], cwd, "Newer", [app.message("user", "needle needle needle")]
    )
    os.utime(session.path, (1, 1))
    monkeypatch.setattr(web, "refreshed", 0.0)

    def refs(**args):
        rows = http.get("/api/sessions", query_string={"q": "needle", **args}).json
        return [r["ref"] for r in rows]

    assert refs(sort="recent") == [newer.ref, session.ref]
    assert refs(sort="recent", limit=1) == [newer.ref]
