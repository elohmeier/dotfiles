import json
import sqlite3

import pytest
import zstandard as zstd

from scripts import agent_session as app
from scripts import agent_session_web as web
from scripts.agent_session_index import Index


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(web, "refreshed", 0.0)
    store = app.Store("codex:host", tmp_path / "codex")
    monkeypatch.setattr(app, "stores", lambda: [store])
    path = store.root / "sessions/rollout.jsonl"
    app.write_jsonl(
        path,
        [
            {
                "type": "session_meta",
                "payload": {"id": "fixture", "cwd": str(tmp_path)},
            },
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "needle café"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "Found it.",
                },
            },
        ],
    )
    with sqlite3.connect(store.root / "state_5.sqlite") as db:
        db.execute(
            "CREATE TABLE threads (id, rollout_path, cwd, title, updated_at, archived, source)"
        )
        db.execute(
            "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("fixture", str(path), str(tmp_path), "Fixture", 123, 0, "cli"),
        )
    return app.Session(store, "fixture", path, tmp_path, "Fixture", 123)


def compress(path):
    compressed = path.with_suffix(".jsonl.zst")
    compressed.write_bytes(zstd.compress(path.read_bytes()))
    path.unlink()
    return compressed


@pytest.mark.parametrize("database", [True, False])
def test_compressed_codex_discovery_search_and_rebuild(session, monkeypatch, database):
    compressed = compress(session.path)
    if not database:
        (session.store.root / "state_5.sqlite").unlink()
    [found] = app.discover(None)
    assert found.ref == session.ref
    assert found.path == session.path
    assert found.message_count == 2
    assert found.first_prompt == "needle café"
    assert found.last_reply == "Found it."
    assert [m.text for m in app.conversation(found)] == ["needle café", "Found it."]
    assert list(app.records(compressed)) == list(app.records(session.path))

    def no_transcript_read(path):
        pytest.fail("An unchanged compressed transcript should not be reopened")

    with Index() as index:
        with monkeypatch.context() as patch:
            patch.setattr(app, "open_transcript", no_transcript_read)
            index.refresh()
        [hit] = index.search("Found", index.sessions())
        assert hit["ref"] == session.ref
        assert hit["match_line"] == 2
        index.refresh(rebuild=True)
        assert index.search("Found", index.sessions()) == [hit]


def test_index_handles_compression_rewrites_and_plain_append(session):
    original = session.path.read_bytes()
    with Index() as index:
        index.refresh()
        compress(session.path)
        index.refresh()
        assert index.sessions()[0].message_count == 2
        assert index.search("needle", index.sessions())

        compressed = session.path.with_suffix(".jsonl.zst")
        # Multiple frames and a rewrite of the same inode must rebuild old search hits.
        extra = (
            json.dumps(
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "appended"},
                }
            ).encode()
            + b"\n"
        )
        compressed.write_bytes(
            zstd.compress(original.replace(b"needle", b"replacement"))
            + zstd.compress(extra)
        )
        index.refresh()
        assert index.search("needle", index.sessions()) == []
        assert index.search("replacement", index.sessions())
        assert index.search("appended", index.sessions())
        assert index.sessions()[0].message_count == 3
        assert [m.text for m in app.conversation(session)] == [
            "replacement café",
            "Found it.",
            "appended",
        ]

        with app.open_transcript(session.path) as file:
            session.path.write_bytes(file.read())
        compressed.unlink()
        index.refresh()
        assert index.sessions()[0].message_count == 3
        with session.path.open("ab") as file:
            file.write(extra.replace(b"appended", b"incremental"))
        index.refresh()
        assert index.sessions()[0].message_count == 4
        assert index.search("incremental", index.sessions())
        assert len(index.sessions()) == 1


def test_plain_rollout_takes_precedence_over_compressed_sibling(session):
    (session.store.root / "state_5.sqlite").unlink()
    session.path.with_suffix(".jsonl.zst").write_bytes(
        zstd.compress(session.path.read_bytes().replace(b"needle", b"obsolete"))
    )
    [found] = app.discover(None)
    assert found.first_prompt == "needle café"
    assert app.conversation(found)[0].text == "needle café"


def test_session_api_reads_compressed_rollouts_and_handles_missing_files(
    session, monkeypatch
):
    server = web.create()
    server.testing = True
    http = server.test_client()
    params = {"ref": session.ref}
    before = http.get("/api/session", query_string=params)
    assert before.status_code == 200
    before_data = before.json
    assert before_data is not None
    compressed = compress(session.path)
    assert http.get("/api/session", query_string=params).json == before_data
    monkeypatch.setattr(web, "refreshed", 0.0)
    response = http.get("/api/session", query_string=params)
    assert response.status_code == 200
    data = response.json
    assert data is not None
    assert data["messages"] == before_data["messages"]
    assert data["session"]["message_count"] == 2
    compressed.unlink()
    assert http.get("/api/session", query_string=params).status_code == 404
    monkeypatch.setattr(web, "refreshed", 0.0)
    assert http.get("/api/session", query_string=params).status_code == 404
