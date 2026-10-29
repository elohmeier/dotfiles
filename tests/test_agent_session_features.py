import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from scripts import agent_session as app
from scripts.agent_session_index import Index, repository, scoped

STAMP = "2026-10-01T12:00:00.000Z"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    stores = [
        app.Store("pi", tmp_path / "pi"),
        app.Store("claude:host", tmp_path / "claude"),
        app.Store("codex:host", tmp_path / "codex"),
    ]
    monkeypatch.setattr(app, "stores", lambda: stores)
    return tmp_path, stores


def append(path, *rows):
    with path.open("a") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def pi_message(id_, text, parent=None, role="user"):
    return {
        "type": "message",
        "id": id_,
        "parentId": parent,
        "timestamp": STAMP,
        "message": {"role": role, "content": text},
    }


def test_middle_title_and_incremental_checkpoint(workspace, monkeypatch):
    cwd, stores = workspace
    session = app.write_pi(
        stores[0], cwd, "Initial name", [app.message("user", "Initial prompt")]
    )
    filler = [{"type": "custom", "data": "x" * 1000}] * 150
    append(
        session.path,
        *filler,
        {"type": "session_info", "name": "Middle rename"},
        *filler,
    )
    assert app.discover(cwd)[0].title == "Middle rename"
    open_file = Path.open

    def no_transcript_read(path, *args, **kwargs):
        assert path != session.path, "An unchanged transcript should not be reopened"
        return open_file(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", no_transcript_read)
        assert app.discover(cwd)[0].title == "Middle rename"
    append(session.path, {"type": "session_info", "name": "Newest rename"})
    assert app.discover(cwd)[0].title == "Newest rename"
    with Index() as index:
        index.refresh()
        before = index.search("Initial", index.sessions())
        index.refresh(rebuild=True)
        assert index.search("Initial", index.sessions()) == before


@pytest.mark.parametrize("replacement", [False, True])
def test_index_detects_rewrites_and_removes_stale_search_hits(workspace, replacement):
    cwd, stores = workspace
    session = app.write_pi(
        stores[0], cwd, "Title", [app.message("user", "obsoleteword")]
    )
    app.discover(None)
    changed = session.path.read_bytes().replace(b"obsoleteword", b"freshnewword")
    if replacement:
        new = session.path.with_suffix(".new")
        new.write_bytes(changed)
        new.replace(session.path)
    else:
        session.path.write_bytes(changed)
    with Index() as index:
        index.refresh()
        assert index.search("obsoleteword", index.sessions()) == []
        assert index.search("freshnewword", index.sessions())[0]["ref"] == session.ref
    session.path.unlink()
    assert app.discover(None) == []


def test_partial_line_is_indexed_once_after_it_finishes(workspace):
    cwd, stores = workspace
    session = app.write_pi(stores[0], cwd, "Title", [app.message("user", "first")])
    app.discover(None)
    row = json.dumps(pi_message("later", "unicorn"))
    with session.path.open("a") as file:
        file.write(row[:30])
    with Index() as index:
        index.refresh()
        assert index.search("unicorn", index.sessions()) == []
    with session.path.open("a") as file:
        file.write(row[30:] + "\n")
    with Index() as index:
        index.refresh()
        index.refresh()
        assert index.sessions()[0].message_count == 2
        assert len(index.search("unicorn", index.sessions())) == 1


def test_search_indexes_tools_but_excludes_results_and_image_data(workspace):
    cwd, stores = workspace
    session = app.write_pi(
        stores[0], cwd, "Title", [app.message("user", "needle migration")]
    )
    append(
        session.path,
        pi_message(
            "call",
            [
                {
                    "type": "toolCall",
                    "id": "call-id",
                    "name": "read",
                    "arguments": {"path": "unique-file.py"},
                }
            ],
        ),
        {
            **pi_message(
                "result", [{"type": "text", "text": "outputsecret"}], role="toolResult"
            ),
            "message": {
                "role": "toolResult",
                "toolCallId": "call-id",
                "toolName": "read",
                "isError": True,
                "content": [{"type": "text", "text": "outputsecret"}],
            },
        },
        pi_message(
            "image",
            [{"type": "image", "data": "imagepayload", "mimeType": "image/png"}],
        ),
    )
    with Index() as index:
        index.refresh()
        sessions = index.sessions()
        assert index.search('"needle migration"', sessions)
        assert index.search("unique-file.py", sessions)[0]["match_line"] is not None
        assert index.search("outputsecret", sessions) == []
        assert index.search("imagepayload", sessions) == []
        assert index.search('OR : "', sessions) == []
    messages = app.conversation(session, context=False)
    call, result = messages[1:3]
    assert call.content[0]["id"] == result.content[0]["id"] == "call-id"
    assert result.content[0]["error"] is True


def test_full_history_retains_old_context_and_abandoned_branches(workspace):
    cwd, stores = workspace
    session = app.write_pi(stores[0], cwd, "Title", [])
    append(
        session.path,
        pi_message("old", "earlier discussion"),
        pi_message("abandoned", "abandoned reply", "old", "assistant"),
        {
            "type": "compaction",
            "id": "compact",
            "parentId": "old",
            "firstKeptEntryId": "compact",
            "summary": "Summary",
        },
        pi_message("latest", "current prompt", "compact"),
    )
    assert [m.text for m in app.conversation(session)] == [
        "[Previous context summary]\nSummary",
        "current prompt",
    ]
    assert [m.text for m in app.conversation(session, context=False)] == [
        "earlier discussion",
        "abandoned reply",
        "[Previous context summary]\nSummary",
        "current prompt",
    ]
    result = CliRunner().invoke(app.main, ["show", session.ref, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["total_messages"] == 4


def test_opaque_history_can_be_read_and_partial_transfer_is_explicit(workspace):
    cwd, stores = workspace
    path = stores[2].root / "sessions" / "opaque.jsonl"
    app.write_jsonl(
        path,
        [
            {"type": "session_meta", "payload": {"id": "opaque", "cwd": str(cwd)}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "old context"},
            },
            {
                "type": "compacted",
                "payload": {
                    "replacement_history": [
                        {"type": "compaction", "encrypted_content": "opaque"}
                    ]
                },
            },
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "readable tail"},
            },
        ],
    )
    source = app.discover(cwd)[0]
    assert "old context" in [m.text for m in app.conversation(source, context=False)]
    with pytest.raises(app.click.ClickException, match="opaque compaction"):
        app.prepare_transfer(source, stores[0])
    messages, report = app.prepare_transfer(source, stores[0], allow_partial=True)
    assert report["partial_context"]
    assert "partial transfer" in messages[0].text
    assert "old context" not in [m.text for m in messages]
    assert messages[-1].text == "readable tail"


def test_json_pages_window_long_messages_without_losing_text():
    messages = [app.message("user", "a" * 200), app.message("assistant", "final")]
    output = []
    cursor = {"start": 0, "offset": 0}
    while cursor is not None:
        page = app.message_page(
            messages, start=cursor["start"], offset=cursor["offset"], chars=47
        )
        assert sum(len(m["text"]) for m in page["messages"]) <= 47
        output.extend(m["text"] for m in page["messages"])
        cursor = page["next"]
    assert "".join(output) == "a" * 200 + "final"
    assert app.message_page(messages, start=-1)["messages"][0]["text"] == "final"


def test_camel_case_inline_image_source():
    msg = app.message(
        "user",
        [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "mediaType": "image/webp",
                    "data": "aW1hZ2U=",
                },
            }
        ],
    )
    assert msg.content == [
        {"type": "image", "mimeType": "image/webp", "data": "aW1hZ2U="}
    ]


@pytest.mark.parametrize("agent", ["pi", "claude:host"])
def test_native_forks_preserve_tools_images_and_lineage(workspace, agent):
    cwd, stores = workspace
    store = next(s for s in stores if s.name == agent)
    writer = app.write_pi if agent == "pi" else app.write_claude
    source = writer(
        store,
        cwd,
        "Title",
        [
            app.message(
                "user",
                [
                    {"type": "text", "text": "question"},
                    {"type": "image", "mimeType": "image/png", "data": "aW1hZ2U="},
                ],
            )
        ],
    )
    if agent == "pi":
        append(
            source.path,
            pi_message(
                "tool",
                [
                    {
                        "type": "toolCall",
                        "id": "native-id",
                        "name": "read",
                        "arguments": {"path": "x"},
                    }
                ],
            ),
        )
    else:
        append(
            source.path,
            {
                "type": "assistant",
                "uuid": "tool",
                "parentUuid": None,
                "sessionId": source.id,
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "native-id",
                            "name": "Read",
                            "input": {"file_path": "x"},
                        }
                    ],
                },
            },
        )
    before = source.path.read_bytes()
    fork = app.copy_session(source, store)
    assert source.path.read_bytes() == before
    assert fork.id != source.id
    assert b"native-id" in fork.path.read_bytes()
    assert b"aW1hZ2U=" in fork.path.read_bytes()
    assert fork.path.stat().st_mode & 0o777 == 0o600
    rows = list(app.records(fork.path))
    if agent == "pi":
        assert rows[0]["parentSession"] == str(source.path)
    else:
        assert all(r["sessionId"] == fork.id for r in rows)
        assert rows[-1]["forkedFrom"]["sessionId"] == source.id
    found = {s.id: s for s in app.discover(cwd)}
    assert found[fork.id].parent == source.ref
    assert found[fork.id].kind == "fork"


def test_large_copy_has_no_default_token_limit(workspace):
    cwd, stores = workspace
    text = "retained context " * 40_000
    source = app.write_pi(stores[0], cwd, "Large session", [app.message("user", text)])
    messages, report = app.prepare_transfer(source, stores[1])
    assert report["estimated_tokens"] > 100_000
    assert report["dropped_messages"] == 0
    assert not report["partial_context"]
    assert messages[-1].text == text
    runner = CliRunner()
    result = runner.invoke(app.main, ["copy", source.ref, "--to", "claude"])
    assert result.exit_code == 0, result.output
    copied = next(s for s in app.discover(cwd) if s.store.agent == "claude")
    assert app.conversation(copied)[-1].text == text
    result = runner.invoke(
        app.main,
        ["copy", source.ref, "--to", "claude", "--max-tokens", "100000"],
    )
    assert result.exit_code == 1
    assert "raise --max-tokens" in result.output


def test_copy_report_budget_redaction_and_dry_run(workspace):
    cwd, stores = workspace
    source = app.write_pi(
        stores[0],
        cwd,
        "Title",
        [
            app.message("user", "old " * 2000),
            app.message("assistant", "old reply"),
            app.message("user", "new prompt token-123"),
        ],
    )
    with pytest.raises(app.click.ClickException, match="max-tokens"):
        app.prepare_transfer(source, stores[1], max_tokens=100)
    messages, report = app.prepare_transfer(
        source, stores[1], max_tokens=256, allow_partial=True, redact=(r"token-\d+",)
    )
    assert report["dropped_messages"] == 2
    assert report["redactions"] == 1
    assert report["estimated_tokens"] <= 256
    assert "token-123" not in "".join(m.text for m in messages)
    before = list(stores[1].root.rglob("*.jsonl"))
    result = CliRunner().invoke(
        app.main, ["copy", source.ref, "--to", "claude", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "text tokens" in result.output
    assert list(stores[1].root.rglob("*.jsonl")) == before


def test_tool_output_limit_zero_is_honored(workspace):
    cwd, stores = workspace
    source = app.write_pi(stores[0], cwd, "Title", [app.message("user", "prompt")])
    append(
        source.path,
        {
            "type": "message",
            "id": "result",
            "parentId": None,
            "timestamp": STAMP,
            "message": {
                "role": "toolResult",
                "toolName": "read",
                "content": "private output",
            },
        },
    )
    result = CliRunner().invoke(
        app.main, ["copy", source.ref, "--to", "claude", "--tool-output-limit", "0"]
    )
    assert result.exit_code == 0, result.output
    copied = next(s for s in app.discover(cwd) if s.store.agent == "claude")
    assert "private output" not in copied.path.read_text()
    assert "Tool output clipped" in copied.path.read_text()


def test_cross_store_fork_keeps_the_original_store_in_its_parent(
    workspace, monkeypatch
):
    cwd, stores = workspace
    target = app.Store("claude:sandbox", cwd / "sandbox")
    monkeypatch.setattr(app, "stores", lambda: [*stores, target])
    source = app.write_claude(stores[1], cwd, "Title", [app.message("user", "prompt")])
    fork = app.fork_session(source, target)
    found = next(s for s in app.discover(cwd) if s.id == fork.id)
    assert found.parent == source.ref


def test_title_priority_and_clearing_a_name(workspace):
    cwd, stores = workspace
    source = app.write_claude(
        stores[1], cwd, "Named", [app.message("user", "First prompt")]
    )
    append(source.path, {"type": "ai-title", "aiTitle": "Generated"})
    assert app.discover(cwd)[0].title == "Named"
    append(source.path, {"type": "custom-title", "customTitle": ""})
    assert app.discover(cwd)[0].title == "Generated"
    append(source.path, {"type": "ai-title", "aiTitle": ""})
    assert app.discover(cwd)[0].title == "First prompt"


def test_recorded_branch_scope_includes_other_worktrees(workspace):
    cwd, stores = workspace
    repo, worktree = cwd / "repo", cwd / "worktree"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "--allow-empty",
        "-m",
        "test",
    )
    git("worktree", "add", "-b", "feature", str(worktree))
    source = app.write_claude(
        stores[1], repo, "Main work", [app.message("user", "main prompt")]
    )
    append(source.path, {"type": "system", "gitBranch": "main"})
    other = app.write_claude(
        stores[1], worktree, "Feature work", [app.message("user", "feature prompt")]
    )
    append(other.path, {"type": "system", "gitBranch": "feature"})
    repository.cache_clear()
    sessions = app.discover(None)
    assert repository(repo) == repository(worktree)
    os.chdir(repo)
    assert {s.id for s in scoped(sessions, "repo")[0]} == {source.id, other.id}
    assert [s.id for s in scoped(sessions, "branch")[0]] == [source.id]
    assert [s.id for s in scoped(sessions, "repo", query="b:feature")[0]] == [other.id]


@pytest.mark.parametrize("shell", ["sh", "fish"])
def test_printed_resume_preserves_cwd_environment_and_literal_arguments(
    workspace, monkeypatch, shell
):
    if not shutil.which(shell):
        pytest.skip(f"{shell} not installed")
    cwd, _ = workspace
    project = cwd / "project ' space"
    project.mkdir()
    executable = cwd / "bin"
    executable.mkdir()
    output = cwd / "result.json"
    shim = executable / "pi"
    shim.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\nPath({str(output)!r}).write_text(json.dumps([os.getcwd(), os.environ['PI_CODING_AGENT_DIR'], sys.argv[1:]]))\n"
    )
    shim.chmod(0o700)
    monkeypatch.setenv("PATH", str(executable) + os.pathsep + os.environ["PATH"])
    session = app.Session(
        app.Store("pi", cwd / "store ' space"),
        "id",
        project / "session.jsonl",
        project,
        "Title",
        0,
    )
    argument = "' $(touch should-not-exist) $HOME"
    command = app.render_resume(session, ("--model", argument))
    subprocess.run(
        [shell, *(["--no-config"] if shell == "fish" else []), "-c", command],
        check=True,
    )
    actual = json.loads(output.read_text())
    assert actual == [
        str(project.resolve()),
        str(session.store.root),
        ["--session", str(session.path), "--model", argument],
    ]
    assert not (project / "should-not-exist").exists()


def test_fzf_picker_returns_a_session_without_a_terminal(workspace, monkeypatch):
    if not shutil.which("fzf"):
        pytest.skip("fzf not installed")
    cwd, stores = workspace
    source = app.write_pi(
        stores[0],
        cwd,
        "Find this session",
        [app.message("user", "unique picker prompt")],
    )
    monkeypatch.setenv("FZF_DEFAULT_OPTS", "--filter=Find")
    result = CliRunner().invoke(app.main, ["--print"])
    assert result.exit_code == 0, result.output
    assert source.id in result.output
    assert shlex.split(result.output)[0] == "cd"


@pytest.mark.skipif(
    not os.environ.get("AGENT_SESSION_NATIVE_TESTS"),
    reason="opt-in installed Codex integration",
)
def test_native_codex_fork_preserves_rollout_and_parent(workspace):
    cwd, stores = workspace
    source = app.write_codex(
        stores[2],
        cwd,
        "Native fork",
        [app.message("user", "remember 42"), app.message("assistant", "42")],
    )
    before = source.path.read_bytes()
    fork = app.fork_session(source)
    assert source.path.read_bytes() == before
    assert fork.id != source.id
    rows = list(app.records(fork.path))
    assert rows[0]["payload"]["forked_from_id"] == source.id
    assert fork.parent == source.ref
    with app.codex(stores[2], cwd) as server:
        thread = server.call(
            "thread/read", {"threadId": fork.id, "includeTurns": True}
        )["thread"]
        assert thread["id"] == fork.id
        assert thread["turns"]


@pytest.mark.skipif(
    not os.environ.get("AGENT_SESSION_NATIVE_TESTS") or not shutil.which("pi"),
    reason="opt-in installed Pi integration",
)
def test_native_pi_can_export_a_fork(workspace):
    cwd, stores = workspace
    source = app.write_pi(
        stores[0],
        cwd,
        "Native Pi",
        [app.message("user", "remember 42"), app.message("assistant", "42")],
    )
    fork = app.fork_session(source)
    output = cwd / "fork.html"
    subprocess.run(
        ["pi", "--export", str(fork.path), str(output)],
        env={
            **stores[0].environment(),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    match = re.search(
        r'<script id="session-data"[^>]*>([^<]+)</script>', output.read_text()
    )
    assert match
    exported = json.loads(base64.b64decode(match[1]))
    assert exported["header"]["parentSession"] == str(source.path)
    assert exported["entries"][0]["message"]["content"][0]["text"] == "remember 42"
