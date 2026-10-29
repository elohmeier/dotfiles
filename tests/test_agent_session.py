import json
import os
import sqlite3
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from scripts import agent_session as app

STAMP = "2026-10-01T12:00:00.000Z"


def pi_entry(id_, parent, role, text) -> app.Record:
    return {
        "type": "message",
        "id": id_,
        "parentId": parent,
        "timestamp": STAMP,
        "message": {"role": role, "content": text},
    }


def claude_entry(id_, parent, role, text, **extra) -> app.Record:
    return {
        "type": role,
        "uuid": id_,
        "parentUuid": parent,
        "timestamp": STAMP,
        "message": {"role": role, "content": text},
        **extra,
    }


def codex_entry(kind, payload) -> app.Record:
    return {"type": kind, "payload": payload, "timestamp": STAMP}


def test_pi_active_branch_compaction_and_context_edits():
    rows = [
        pi_entry("old", None, "user", "discarded context"),
        pi_entry("kept", "old", "user", "retained question"),
        pi_entry("abandoned", "kept", "assistant", "abandoned branch"),
        {
            "type": "compaction",
            "id": "summary",
            "parentId": "kept",
            "summary": "earlier decisions",
            "firstKeptEntryId": "kept",
        },
        pi_entry("answer", "summary", "assistant", "original answer"),
        {
            "type": "context_edit",
            "id": "edit",
            "parentId": "answer",
            "targetId": "answer",
            "replacement": {"content": "corrected answer"},
        },
    ]
    assert [m.text for m in app.read_pi(rows)] == [
        "[Previous context summary]\nearlier decisions",
        "retained question",
        "corrected answer",
    ]


def test_pi_omitted_context_and_shell_history():
    rows: list[app.Record] = [
        pi_entry("question", None, "user", "remove me"),
        {
            "type": "context_edit",
            "id": "edit",
            "parentId": "question",
            "targetId": "question",
            "replacement": None,
        },
        pi_entry("shell", "edit", "bashExecution", ""),
    ]
    rows[-1]["message"].update(
        command="pwd", output="/project", excludeFromContext=False
    )
    assert [m.text for m in app.read_pi(rows)] == [
        "[Historical shell command]\npwd\n/project"
    ]


def test_claude_preserved_segment_and_sidechain():
    rows = [
        claude_entry("old", None, "user", "discarded context"),
        claude_entry("kept", "old", "assistant", "retained evidence"),
        {
            "type": "system",
            "subtype": "compact_boundary",
            "uuid": "boundary",
            "parentUuid": None,
            "compactMetadata": {
                "preservedMessages": {"anchorUuid": "summary", "allUuids": ["kept"]}
            },
        },
        claude_entry(
            "summary",
            "boundary",
            "user",
            "earlier decisions",
            isCompactSummary=True,
            isMeta=True,
        ),
        claude_entry("question", "summary", "user", "continue"),
        claude_entry("side", None, "assistant", "subagent", isSidechain=True),
    ]
    assert [m.text for m in app.read_claude(rows)] == [
        "earlier decisions",
        "retained evidence",
        "continue",
    ]


def test_codex_canonical_users_are_not_duplicated_and_tools_are_inert():
    rows = [
        codex_entry(
            "response_item",
            {
                "type": "message",
                "role": "developer",
                "content": "old agent instructions",
            },
        ),
        codex_entry(
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": "# AGENTS.md instructions for /project",
            },
        ),
        codex_entry(
            "response_item", {"type": "message", "role": "user", "content": "question"}
        ),
        codex_entry(
            "event_msg",
            {
                "type": "item_completed",
                "item": {
                    "type": "UserMessage",
                    "content": [{"type": "text", "text": "question"}],
                },
            },
        ),
        codex_entry(
            "event_msg",
            {
                "type": "item_completed",
                "item": {
                    "type": "AgentMessage",
                    "content": [{"type": "Text", "text": "answer"}],
                },
            },
        ),
        codex_entry(
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "answer"}],
            },
        ),
        codex_entry(
            "response_item",
            {"type": "custom_tool_call", "name": "exec", "input": "pwd"},
        ),
        codex_entry(
            "response_item", {"type": "custom_tool_call_output", "output": "/project"}
        ),
    ]
    assert [m.text for m in app.read_codex(rows)] == [
        "question",
        "answer",
        "[Historical tool call: exec]\npwd",
        "[Historical tool result]\n/project",
    ]


def test_codex_compaction_replaces_old_context():
    rows = [
        codex_entry(
            "compacted",
            {
                "replacement_history": [
                    {"type": "compaction", "encrypted_content": "old opaque context"}
                ]
            },
        ),
        codex_entry(
            "response_item", {"type": "message", "role": "user", "content": "discarded"}
        ),
        codex_entry(
            "compacted",
            {
                "replacement_history": [
                    {"type": "message", "role": "user", "content": "summary"}
                ]
            },
        ),
        codex_entry("event_msg", {"type": "user_message", "message": "continue"}),
    ]
    assert [m.text for m in app.read_codex(rows)] == ["summary", "continue"]


def test_claude_tool_results_are_evidence_not_user_instructions():
    rows = [
        claude_entry(
            "result",
            None,
            "user",
            [{"type": "tool_result", "content": "done", "tool_use_id": "old-call"}],
        )
    ]
    messages = app.read_claude(rows)
    assert messages[0].role == "assistant"
    assert messages[0].text == "[Historical tool result]\ndone"


def test_pi_uses_destination_model_selection(tmp_path):
    root = tmp_path / "pi"
    root.mkdir()
    (root / "settings.json").write_text(
        json.dumps(
            {
                "defaultProvider": "destination-provider",
                "defaultModel": "destination-model",
            }
        )
    )
    copied = app.write_pi(
        app.Store("pi", root),
        tmp_path,
        "Fixture",
        [app.message("assistant", "old answer")],
    )
    changes = [r for r in app.records(copied.path) if r["type"] == "model_change"]
    assert changes[-1]["provider"] == "destination-provider"
    assert changes[-1]["modelId"] == "destination-model"


def test_opaque_compaction_is_not_silently_dropped():
    with pytest.raises(app.click.ClickException, match="opaque compaction"):
        app.read_codex(
            [
                codex_entry(
                    "compacted",
                    {
                        "replacement_history": [
                            {"type": "compaction", "encrypted_content": "opaque"}
                        ]
                    },
                )
            ]
        )


@pytest.mark.parametrize("writer", [app.write_claude, app.write_pi])
def test_native_file_writers_retain_images_and_private_permissions(tmp_path, writer):
    agent = "pi" if writer == app.write_pi else "claude"
    store = app.Store(agent, tmp_path / agent)
    content = [
        app.text_block("question"),
        {"type": "image", "mimeType": "image/png", "data": "aW1hZ2U="},
    ]
    session = writer(
        store,
        tmp_path,
        "Named session",
        [app.Message("user", content), app.message("assistant", "answer")],
    )
    assert app.conversation(session)[0].content == content
    assert app.conversation(session)[1].text == "answer"
    assert session.path.stat().st_mode & 0o777 == 0o600


def make_source(tmp_path, agent):
    cwd = tmp_path.resolve()
    if agent in {"claude", "pi"}:
        writer = app.write_claude if agent == "claude" else app.write_pi
        return writer(
            app.Store(agent, tmp_path / f"source-{agent}"),
            cwd,
            "Fixture",
            [
                app.message("user", "Remember value 42."),
                app.message("assistant", "Value 42 is retained."),
            ],
        )
    path = tmp_path / "source-codex.jsonl"
    app.write_jsonl(
        path,
        [
            codex_entry(
                "event_msg", {"type": "user_message", "message": "Remember value 42."}
            ),
            codex_entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "Value 42 is retained.",
                },
            ),
        ],
    )
    return app.Session(
        app.Store("codex:host", tmp_path), "source-id", path, cwd, "Fixture", 0
    )


@pytest.mark.parametrize(
    ("source_agent", "target_agent"),
    [(a, b) for a in ("claude", "pi", "codex") for b in ("claude", "pi") if a != b],
)
def test_cross_agent_copy_keeps_source_and_provenance(
    tmp_path, source_agent, target_agent
):
    source = make_source(tmp_path, source_agent)
    before = source.path.read_bytes()
    copied = app.copy_session(
        source, app.Store(target_agent, tmp_path / f"target-{target_agent}")
    )
    assert copied.id != source.id
    assert source.path.read_bytes() == before
    messages = app.conversation(copied)
    assert source.ref in messages[0].text
    assert [m.text for m in messages[1:]] == [
        "Remember value 42.",
        "Value 42 is retained.",
    ]


def test_discovery_uses_recorded_cwd_and_excludes_subagents(tmp_path, monkeypatch):
    cwd = tmp_path.resolve()
    store = app.Store("claude:host", tmp_path / "claude")
    source = app.write_claude(
        store, cwd, "Named session", [app.message("user", "question")]
    )
    renamed = source.path.parent.with_name("not-a-decodable-directory")
    source.path.parent.rename(renamed)
    app.write_jsonl(
        renamed / "subagents/child.jsonl",
        [claude_entry("child", None, "user", "child", cwd=str(cwd))],
    )
    monkeypatch.setattr(app, "stores", lambda: [store])
    sessions = app.discover(cwd)
    assert [(s.id, s.title) for s in sessions] == [(source.id, "Named session")]
    assert app.discover(tmp_path / "elsewhere") == []
    runner = CliRunner()
    assert (
        json.loads(runner.invoke(app.main, ["list", "--all", "--json"]).output)[0][
            "ref"
        ]
        == sessions[0].ref
    )


def test_codex_sandbox_paths_and_source_filter(tmp_path, monkeypatch):
    root = tmp_path / "codex"
    root.mkdir()
    with sqlite3.connect(root / "state_5.sqlite") as db:
        db.execute(
            "CREATE TABLE threads (id, rollout_path, cwd, name, title, updated_at, archived, source)"
        )
        db.executemany(
            "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "main",
                    "/home/piuser/.codex/sessions/main.jsonl",
                    str(tmp_path),
                    None,
                    "Title",
                    2,
                    0,
                    "cli",
                ),
                (
                    "child",
                    "child.jsonl",
                    str(tmp_path),
                    None,
                    "Child",
                    1,
                    0,
                    '{"subagent":"review"}',
                ),
                ("archived", "old.jsonl", str(tmp_path), None, "Old", 0, 1, "cli"),
            ],
        )
    monkeypatch.setattr(app, "stores", lambda: [app.Store("codex:sandbox", root)])
    sessions = app.discover(tmp_path.resolve())
    assert len(sessions) == 1
    assert sessions[0].path == root / "sessions/main.jsonl"


def test_store_launch_commands_keep_sandbox_identity(tmp_path):
    store = app.Store("codex:sandbox", tmp_path)
    assert store.command("resume", "id") == [
        "mise",
        "run",
        "agent:codex",
        "--",
        "resume",
        "id",
    ]


@pytest.mark.parametrize(
    ("store_name", "resume_args"),
    [
        ("claude:host", ["--resume", "session-id"]),
        ("claude:sandbox", ["--resume", "session-id"]),
        ("pi", ["--session", "session.jsonl"]),
        ("codex:host", ["resume", "session-id"]),
        ("codex:sandbox", ["resume", "session-id"]),
    ],
)
@pytest.mark.parametrize("agent_args", [[], ["--model", "model with spaces"]])
def test_resume_cli_preserves_store_cwd_and_agent_arguments(
    tmp_path, monkeypatch, store_name, resume_args, agent_args
):
    store = app.Store(store_name, tmp_path / "store")
    session = app.Session(
        store, "session-id", app.Path("session.jsonl"), tmp_path, "Fixture", 0
    )
    monkeypatch.setattr(app, "discover", lambda _: [session])
    run = Mock()
    monkeypatch.setattr(app.subprocess, "run", run)
    result = CliRunner().invoke(app.main, ["resume", session.ref, "--", *agent_args])
    assert result.exit_code == 0, result.output
    run.assert_called_once_with(
        store.command(*resume_args, *agent_args),
        cwd=tmp_path,
        env=store.environment(),
        check=True,
    )


@pytest.mark.parametrize("destination", ["codex", "codex:sandbox"])
@pytest.mark.parametrize("agent_args", [None, [], ["--yolo", "--model", "my model"]])
def test_copy_cli_resumes_imported_session(
    tmp_path, monkeypatch, destination, agent_args
):
    source = make_source(tmp_path, "claude")
    store_name = "codex:host" if destination == "codex" else destination
    store = app.Store(store_name, tmp_path / "codex")
    copied = app.Session(
        store, "imported-id", tmp_path / "imported.jsonl", source.cwd, "Imported", 0
    )
    monkeypatch.setattr(app, "discover", lambda _: [source])
    monkeypatch.setattr(app, "stores", lambda: [store])
    copy = Mock(return_value=copied)
    run = Mock()
    monkeypatch.setattr(app, "copy_session", copy)
    monkeypatch.setattr(app.subprocess, "run", run)
    args = ["copy", source.ref, "--to", destination]
    if agent_args is not None:
        args.extend(["--resume", "--", *agent_args])
    result = CliRunner().invoke(app.main, args)
    assert result.exit_code == 0, result.output
    copy.assert_called_once_with(source, store)
    if agent_args is None:
        run.assert_not_called()
    else:
        run.assert_called_once_with(
            store.command("resume", copied.id, *agent_args),
            cwd=source.cwd,
            env=store.environment(),
            check=True,
        )


def test_copy_rejects_agent_arguments_without_resume(monkeypatch):
    copy = Mock()
    monkeypatch.setattr(app, "copy_session", copy)
    result = CliRunner().invoke(
        app.main, ["copy", "source", "--to", "codex", "--", "--yolo"]
    )
    assert result.exit_code == 2
    assert "Agent arguments require --resume" in result.output
    copy.assert_not_called()


@pytest.mark.skipif(
    not os.environ.get("AGENT_SESSION_NATIVE_TESTS"),
    reason="opt-in installed Codex integration",
)
@pytest.mark.parametrize("agent", ["claude", "pi"])
def test_native_codex_copy_is_listed_readable_and_resumable(tmp_path, agent):
    source = make_source(tmp_path, agent)
    store = app.Store("codex:host", tmp_path / "target-codex")
    copied = app.copy_session(source, store)
    assert [m.text for m in app.conversation(copied)][-2:] == [
        "Remember value 42.",
        "Value 42 is retained.",
    ]
    with app.codex(store, tmp_path.resolve()) as server:
        listed = server.call(
            "thread/list", {"cwd": str(tmp_path.resolve()), "limit": 20}
        )
        assert copied.id in [s["id"] for s in listed["data"]]
        thread = server.call(
            "thread/read", {"threadId": copied.id, "includeTurns": True}
        )["thread"]
        assert any(turn["items"] for turn in thread["turns"])
        resumed = server.call(
            "thread/resume", {"threadId": copied.id, "excludeTurns": True}
        )
        assert resumed["thread"]["id"] == copied.id
