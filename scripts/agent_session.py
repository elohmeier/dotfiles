"""Browse and copy Claude Code, Pi and Codex conversations between local stores."""

import json
import os
import re
import selectors
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import questionary
import rich_click as click
from click.shell_completion import CompletionItem
from rich.console import Console
from rich.table import Table
from rich.text import Text

Record = dict[str, Any]
console = Console(highlight=False)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Store:
    name: str
    root: Path

    @property
    def agent(self) -> str:
        return self.name.split(":")[0]

    def command(self, *args: str) -> list[str]:
        if self.name.endswith(":sandbox"):
            return ["mise", "run", f"agent:{self.agent}", "--", *args]
        return [self.agent, *args]

    def environment(self) -> dict[str, str]:
        # Claude's unset default uses ~/.claude.json; an explicit directory moves it.
        if (
            self.agent == "claude"
            and self.root == Path.home() / ".claude"
            and self.variable not in os.environ
        ):
            return dict(os.environ)
        return {**os.environ, self.variable: str(self.root)}

    @property
    def variable(self) -> str:
        return {
            "claude": "CLAUDE_CONFIG_DIR",
            "pi": "PI_CODING_AGENT_DIR",
            "codex": "CODEX_HOME",
        }[self.agent]

    def runtime_path(self, path: Path) -> str:
        return (
            str(path).replace(str(self.root), f"/home/piuser/.{self.agent}", 1)
            if self.name.endswith(":sandbox")
            else str(path)
        )


def stores() -> list[Store]:
    home = Path.home()
    sandbox = (
        Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "agent-sandbox"
    )
    return [
        Store(
            "claude:host",
            Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")).expanduser(),
        ),
        Store(
            "pi",
            Path(
                os.environ.get("PI_CODING_AGENT_DIR", home / ".pi/agent")
            ).expanduser(),
        ),
        Store(
            "codex:host",
            Path(os.environ.get("CODEX_HOME", home / ".codex")).expanduser(),
        ),
        Store("claude:sandbox", sandbox / "claude/.claude"),
        Store("codex:sandbox", sandbox / "codex/.codex"),
    ]


@dataclass
class Session:
    store: Store
    id: str
    path: Path
    cwd: Path
    title: str
    updated: float
    branch: str = ""
    model: str = ""
    repo: str = ""
    parent: str = ""
    kind: str = ""
    message_count: int = 0
    first_prompt: str = ""
    last_reply: str = ""

    @property
    def ref(self) -> str:
        return f"{self.store.name}:{self.id}"

    def data(self) -> Record:
        return {
            **{k: v for k, v in asdict(self).items() if k != "store"},
            "ref": self.ref,
            "path": str(self.path),
            "cwd": str(self.cwd),
            "store": self.store.name,
        }


@dataclass
class Message:
    role: str
    content: list[Record]
    timestamp: str = ""
    id: str = ""
    line: int = -1

    @property
    def text(self) -> str:
        return render(self.content)


def text_block(text: str) -> Record:
    return {"type": "text", "text": text}


def records(path: Path) -> Iterator[Record]:
    with path.open() as file:
        for line in file:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A running agent may not have finished its last JSONL record.
                continue


def candidates() -> Iterator[tuple[Store, Path, Record]]:
    for store in stores():
        databases = sorted(
            store.root.glob("state_*.sqlite"), key=lambda p: int(p.stem.split("_")[-1])
        )
        if store.agent == "codex" and databases:
            with sqlite3.connect(f"{databases[-1].as_uri()}?mode=ro", uri=True) as db:
                db.row_factory = sqlite3.Row
                for row in db.execute(
                    "SELECT * "
                    "FROM threads WHERE archived=0 AND source NOT LIKE '%subagent%'"
                ):
                    data = dict(row)
                    path = str(data["rollout_path"]).replace(
                        "/home/piuser/.codex/", f"{store.root}/", 1
                    )
                    yield (
                        store,
                        Path(path),
                        {
                            "id": data["id"],
                            "cwd": data["cwd"],
                            "title": data.get("name") or data.get("title") or "",
                            "updated": data["updated_at"],
                            **{
                                k: data[column]
                                for k, column in [
                                    ("branch", "git_branch"),
                                    ("model", "model"),
                                ]
                                if data.get(column)
                            },
                        },
                    )
            continue
        root = store.root / ("projects" if store.agent == "claude" else "sessions")
        if store.agent == "pi":
            root = Path(
                os.environ.get("PI_CODING_AGENT_SESSION_DIR", root)
            ).expanduser()
        pattern = "*/*.jsonl" if store.agent == "claude" else "**/*.jsonl"
        for path in root.glob(pattern):
            yield store, path, {}


def discover(cwd: Path | None) -> list[Session]:
    from scripts.agent_session_index import Index

    with Index() as index:
        index.refresh()
        return [s for s in index.sessions() if cwd is None or s.cwd.resolve() == cwd]


def normalize(content: Any) -> list[Record]:
    """Keep tool associations and errors until the destination renders them."""
    if isinstance(content, str):
        return [text_block(content)] if content else []
    result = []
    for block in content or []:
        kind = block.get("type", "")
        if kind in {"text", "Text", "input_text", "output_text"}:
            result.append(text_block(block.get("text", "")))
        elif kind in {"tool_use", "toolCall"}:
            result.append(
                {
                    "type": "tool_call",
                    "id": block.get("id", ""),
                    "name": block["name"],
                    "input": block.get("input", block.get("arguments", {})),
                }
            )
        elif kind == "tool_result":
            if "output" in block:
                result.append(block)
            else:
                result.append(
                    {
                        "type": "tool_result",
                        "id": block.get("tool_use_id", ""),
                        "output": normalize(block.get("content", "")),
                        "error": block.get("is_error", False),
                    }
                )
        elif kind in {"tool_call", "summary", "error", "opaque"}:
            result.append(block)
        elif kind == "image":
            source = block.get("source", {})
            if source.get("type") == "base64":
                result.append(
                    {
                        "type": "image",
                        "data": source["data"],
                        "mimeType": source.get("media_type") or source["mediaType"],
                    }
                )
            elif "data" in block:
                result.append(block)
            else:
                result.append(text_block("[Image omitted: no inline image data]"))
        elif kind == "input_image":
            url = block.get("image_url", "")
            if url.startswith("data:") and ";base64," in url:
                media, data = url[5:].split(";base64,", 1)
                result.append({"type": "image", "data": data, "mimeType": media})
            else:
                result.append(text_block("[Image omitted: external image reference]"))
        elif kind not in {"thinking", "redacted_thinking"}:
            result.append(text_block(f"[Unsupported content omitted: {kind}]"))
    return result


def render(content: list[Record], *, folded: bool = False) -> str:
    parts = []
    for b in content:
        kind = b["type"]
        if kind == "tool_call":
            label = f"[Historical tool call: {b['name']}]"
            value = (
                b["input"]
                if isinstance(b["input"], str)
                else json.dumps(b["input"], ensure_ascii=False)
            )
            parts.append(label if folded else f"{label}\n{value}")
        elif kind == "tool_result":
            label = (
                f"[Historical tool result{': ' + b['name'] if b.get('name') else ''}]"
            )
            output = b["output"]
            value = (
                render(output)
                if isinstance(output, list)
                else output
                if isinstance(output, str)
                else json.dumps(output, ensure_ascii=False)
            )
            parts.append(
                f"{label}{' (error)' if b.get('error') else ''}"
                + ("" if folded else f"\n{value}")
            )
        elif kind == "summary":
            parts.append(
                b["text"]
                if b.get("wrapped")
                else f"[Previous context summary]\n{b['text']}"
            )
        elif kind != "image":
            parts.append(b.get("text", ""))
    return "\n\n".join(parts)


def flatten(content: Any) -> tuple[str, list[Record]]:
    blocks = normalize(content)
    return render(blocks), [b for b in blocks if b["type"] == "image"]


def message(role: str, content: Any, timestamp: str = "") -> Message:
    return Message(role, normalize(content), timestamp)


def branch(rows: list[Record], id_key: str, parent_key: str) -> list[Record]:
    by_id = {row[id_key]: row for row in rows if id_key in row}
    path = []
    node = next(
        (
            r
            for r in reversed(by_id.values())
            if parent_key in r or r.get("type") in {"user", "assistant", "message"}
        ),
        None,
    )
    seen = set()
    while node and node[id_key] not in seen:
        path.append(node)
        seen.add(node[id_key])
        node = by_id.get(node.get(parent_key))
    return path[::-1]


def read_pi(rows: list[Record], *, context: bool = True) -> list[Message]:
    path = (
        branch([r for r in rows if r["type"] != "session"], "id", "parentId")
        if context
        else rows
    )
    edits = {
        r["targetId"]: r["replacement"] for r in path if r["type"] == "context_edit"
    }
    compact = next(
        (i for i in reversed(range(len(path))) if path[i]["type"] == "compaction"), None
    )
    if context and compact is not None:
        checkpoint = path[compact]
        kept = next(
            (
                i
                for i, row in enumerate(path[:compact])
                if row["id"] == checkpoint["firstKeptEntryId"]
            ),
            compact,
        )
        path = [checkpoint, *path[kept:compact], *path[compact + 1 :]]
    result = []
    for row in path:
        before = len(result)
        if context and row.get("id") in edits:
            replacement = edits[row["id"]]
            if replacement is None:
                continue
            row = {
                **row,
                "message": {
                    **row.get("message", {}),
                    "content": replacement["content"],
                },
                "content": replacement["content"],
            }
        if row["type"] in {"compaction", "branch_summary"}:
            result.append(
                message("user", [{"type": "summary", "text": row["summary"]}])
            )
        elif row["type"] == "custom_message":
            result.append(message("user", row["content"]))
        elif row["type"] == "message":
            msg = row["message"]
            role = msg["role"]
            if role in {"user", "assistant", "custom"}:
                result.append(
                    message(
                        "user" if role == "custom" else role,
                        msg["content"],
                        str(row.get("timestamp", "")),
                    )
                )
            elif role == "toolResult":
                converted = message(
                    "assistant",
                    [
                        {
                            "type": "tool_result",
                            "id": msg.get("toolCallId", ""),
                            "name": msg["toolName"],
                            "output": normalize(msg["content"]),
                            "error": msg.get("isError", False),
                        }
                    ],
                    str(row.get("timestamp", "")),
                )
                result.append(converted)
            elif role == "bashExecution" and not msg.get("excludeFromContext"):
                result.append(
                    message(
                        "assistant",
                        f"[Historical shell command]\n{msg['command']}\n{msg['output']}",
                    )
                )
        for msg in result[before:]:
            msg.id, msg.line = row.get("id", ""), row.get("_line", -1)
    return result


def read_claude(rows: list[Record], *, context: bool = True) -> list[Message]:
    rows = [r for r in rows if not r.get("isSidechain")]
    path = branch(rows, "uuid", "parentUuid") if context else rows
    by_id = {r["uuid"]: r for r in rows if "uuid" in r}
    # Claude reconnects preserved pre-compaction messages after its summary in memory.
    for row in path[:] if context else []:
        if row.get("subtype") == "compact_boundary":
            metadata = row.get("compactMetadata", {})
            preserved = metadata.get(
                "preservedMessages", metadata.get("preservedSegment", {})
            )
            anchor = next(
                (
                    i
                    for i, r in enumerate(path)
                    if r["uuid"] == preserved.get("anchorUuid")
                ),
                None,
            )
            if anchor is not None:
                existing = {r["uuid"] for r in path}
                ids = preserved.get("allUuids", preserved.get("uuids", []))
                if not ids and preserved.get("tailUuid") in by_id:
                    kept = branch(
                        list(by_id.values())[
                            : list(by_id).index(preserved["tailUuid"]) + 1
                        ],
                        "uuid",
                        "parentUuid",
                    )
                    ids = [r["uuid"] for r in kept]
                    if preserved.get("headUuid") in ids:
                        ids = ids[ids.index(preserved["headUuid"]) :]
                path[anchor + 1 : anchor + 1] = [
                    by_id[id_] for id_ in ids if id_ in by_id and id_ not in existing
                ]
    result = []
    for r in path:
        if r["type"] not in {"user", "assistant"} or (
            r.get("isMeta") and not r.get("isCompactSummary")
        ):
            continue
        converted = message(
            "assistant"
            if isinstance(r["message"]["content"], list)
            and r["message"]["content"]
            and all(b.get("type") == "tool_result" for b in r["message"]["content"])
            else r["type"],
            [{"type": "summary", "text": flatten(r["message"]["content"])[0]}]
            if r.get("isCompactSummary")
            else r["message"]["content"],
            r.get("timestamp", ""),
        )
        # Claude already labels these summaries in their text.
        if r.get("isCompactSummary"):
            converted.content = [
                {
                    "type": "summary",
                    "text": flatten(r["message"]["content"])[0],
                    "wrapped": True,
                }
            ]
        converted.id = r.get("uuid", "")
        converted.line = r.get("_line", -1)
        result.append(converted)
    return result


def read_codex(
    rows: list[Record],
    *,
    context: bool = True,
    allow_partial: bool = False,
    user_events: bool | None = None,
) -> list[Message]:
    start = next(
        (i for i in reversed(range(len(rows))) if rows[i]["type"] == "compacted"), 0
    )
    rows = rows[start:] if context else rows
    result = []
    has_user_events = (
        user_events
        if user_events is not None
        else any(
            r.get("type") == "event_msg"
            and (
                r["payload"].get("type") == "user_message"
                or r["payload"].get("item", {}).get("type") == "UserMessage"
            )
            for r in rows
        )
    )

    def append(item: Record, timestamp: str, checkpoint: bool = False) -> None:
        kind = item.get("type")
        if kind == "message" and item.get("role") in {"user", "assistant"}:
            if item["role"] == "user" and has_user_events and not checkpoint:
                return
            converted = message(item["role"], item.get("content", ""), timestamp)
            if not converted.text.startswith(
                ("# AGENTS.md instructions", "<environment_context>")
            ):
                result.append(converted)
        elif kind in {"function_call", "custom_tool_call"}:
            result.append(
                message(
                    "assistant",
                    [
                        {
                            "type": "tool_call",
                            "id": item.get("call_id", ""),
                            "name": item.get("name", "tool"),
                            "input": item.get("arguments", item.get("input", "")),
                        }
                    ],
                    timestamp,
                )
            )
        elif kind in {"function_call_output", "custom_tool_call_output"}:
            output = item.get("output", "")
            converted = message(
                "assistant",
                [
                    {
                        "type": "tool_result",
                        "id": item.get("call_id", ""),
                        "output": normalize(output)
                        if isinstance(output, list)
                        else output,
                        "error": isinstance(output, dict)
                        and bool(output.get("exit_code")),
                    }
                ],
                timestamp,
            )
            result.append(converted)
        elif kind in {"compaction", "context_compaction"}:
            opaque(timestamp)

    def opaque(timestamp: str) -> None:
        if context and not allow_partial:
            raise click.ClickException(
                "This Codex context contains an opaque compaction; use --allow-partial to carry only readable context."
            )
        if context:
            result.clear()
        result.append(
            message(
                "user",
                [
                    {
                        "type": "opaque",
                        "text": "[Earlier context unavailable: opaque compaction; only readable context follows.]",
                    }
                ],
                timestamp,
            )
        )

    for row in rows:
        data, timestamp = row.get("payload", {}), row.get("timestamp", "")
        if row.get("metadata", {}).get("compaction_output"):
            continue
        before = len(result)
        if row["type"] == "compacted":
            if context:
                result.clear()
                before = 0
            if context and data.get("replacement_history") is not None:
                for item in data["replacement_history"]:
                    append(item, timestamp, checkpoint=True)
            elif data.get("message"):
                result.append(
                    message(
                        "user",
                        [{"type": "summary", "text": data["message"]}],
                        timestamp,
                    )
                )
            else:
                opaque(timestamp)
        elif row["type"] == "response_item":
            append(data, timestamp)
        elif row["type"] == "event_msg":
            item = data.get("item", {})
            if data.get("type") == "user_message":
                result.append(message("user", data["message"], timestamp))
            elif item.get("type") == "UserMessage":
                result.append(message("user", item["content"], timestamp))
        for msg in result[before:]:
            msg.id = data.get("id", data.get("item", {}).get("id", ""))
            msg.line = row.get("_line", -1)
    return result


def conversation(
    session: Session, *, context: bool = True, allow_partial: bool = False
) -> list[Message]:
    readers = {"pi": read_pi, "claude": read_claude, "codex": read_codex}
    rows = [{**r, "_line": i} for i, r in enumerate(records(session.path))]
    return [
        m
        for m in readers[session.store.agent](
            rows,
            context=context,
            **(
                {"allow_partial": allow_partial}
                if session.store.agent == "codex"
                else {}
            ),
        )
        if m.content
    ]


def write_jsonl(path: Path, rows: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_claude(
    store: Store, cwd: Path, title: str, messages: list[Message]
) -> Session:
    id_, timestamp, parent = str(uuid4()), now(), None
    encoded = re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
    if len(encoded) > 200:
        value = 0
        for char in str(cwd):
            value = (value * 31 + ord(char)) & 0xFFFFFFFF
        value = min(value, 0x100000000 - value)
        suffix = ""
        while value:
            value, digit = divmod(value, 36)
            suffix = "0123456789abcdefghijklmnopqrstuvwxyz"[digit] + suffix
        encoded = f"{encoded[:200]}-{suffix or '0'}"
    path = store.root / "projects" / encoded / f"{id_}.jsonl"
    rows = []
    for msg in messages:
        uuid = str(uuid4())
        content = [
            (
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": b["mimeType"],
                        "data": b["data"],
                    },
                }
                if b["type"] == "image"
                else b
            )
            for b in msg.content
        ]
        body: Record = {"role": msg.role, "content": content}
        if msg.role == "assistant":
            body.update(
                id=f"msg_{uuid4().hex}",
                type="message",
                stop_reason="end_turn",
                stop_sequence=None,
                usage={"input_tokens": 0, "output_tokens": 0},
            )
        rows.append(
            {
                "type": msg.role,
                "uuid": uuid,
                "parentUuid": parent,
                "sessionId": id_,
                "cwd": str(cwd),
                "timestamp": msg.timestamp or timestamp,
                "isSidechain": False,
                "userType": "external",
                "entrypoint": "cli",
                "message": body,
            }
        )
        parent = uuid
    rows.append({"type": "custom-title", "sessionId": id_, "customTitle": title})
    write_jsonl(path, rows)
    return Session(store, id_, path, cwd, title, path.stat().st_mtime)


def write_pi(store: Store, cwd: Path, title: str, messages: list[Message]) -> Session:
    id_, timestamp, parent = str(uuid4()), now(), None
    encoded = "--" + re.sub(r"[/\\:]", "-", str(cwd).lstrip("/\\")) + "--"
    root = Path(
        os.environ.get("PI_CODING_AGENT_SESSION_DIR", store.root / "sessions" / encoded)
    ).expanduser()
    path = root / f"{re.sub(r'[:.]', '-', timestamp)}_{id_}.jsonl"
    rows: list[Record] = [
        {
            "type": "session",
            "version": 3,
            "id": id_,
            "timestamp": timestamp,
            "cwd": str(cwd),
        }
    ]
    for msg in messages:
        entry_id = uuid4().hex[:8]
        body: Record = {
            "role": msg.role,
            "content": msg.content,
            "timestamp": int(
                datetime.fromisoformat(msg.timestamp or timestamp).timestamp() * 1000
            ),
        }
        if msg.role == "assistant":
            body.update(
                api="imported",
                provider="imported",
                model="imported",
                stopReason="stop",
                usage={
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 0,
                    "cost": {
                        "input": 0,
                        "output": 0,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "total": 0,
                    },
                },
            )
        rows.append(
            {
                "type": "message",
                "id": entry_id,
                "parentId": parent,
                "timestamp": msg.timestamp or timestamp,
                "message": body,
            }
        )
        parent = entry_id
    settings = {}
    for config in [store.root / "settings.json", cwd / ".pi/settings.json"]:
        if config.exists():
            settings.update(json.loads(config.read_text()))
    if settings.get("defaultProvider") and settings.get("defaultModel"):
        entry_id = uuid4().hex[:8]
        rows.append(
            {
                "type": "model_change",
                "id": entry_id,
                "parentId": parent,
                "timestamp": timestamp,
                "provider": settings["defaultProvider"],
                "modelId": settings["defaultModel"],
            }
        )
        parent = entry_id
    rows.append(
        {
            "type": "session_info",
            "id": uuid4().hex[:8],
            "parentId": parent,
            "timestamp": timestamp,
            "name": title,
        }
    )
    write_jsonl(path, rows)
    return Session(store, id_, path, cwd, title, path.stat().st_mtime)


class Codex:
    def __init__(self, store: Store, cwd: Path):
        self.process = subprocess.Popen(
            store.command("app-server"),
            cwd=cwd,
            env=store.environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self.serial = 0

    def send(self, value: Record) -> None:
        assert self.process.stdin
        self.process.stdin.write((json.dumps(value) + "\n").encode())
        self.process.stdin.flush()

    def receive(self) -> Record:
        assert self.process.stdout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(60):
                raise click.ClickException(
                    "Codex app-server did not respond within 60 seconds."
                )
        line = self.process.stdout.readline()
        if not line:
            raise click.ClickException(
                "Codex app-server exited before completing the import."
            )
        return json.loads(line)

    def call(self, method: str, params: Record) -> Record:
        self.serial += 1
        self.send({"id": self.serial, "method": method, "params": params})
        while True:
            response = self.receive()
            if response.get("id") == self.serial:
                if "error" in response:
                    raise click.ClickException(response["error"]["message"])
                return response["result"]

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


@contextmanager
def codex(store: Store, cwd: Path) -> Iterator[Codex]:
    server = Codex(store, cwd)
    try:
        server.call(
            "initialize",
            {
                "clientInfo": {"name": "agent-session", "version": "1.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        server.send({"method": "initialized"})
        yield server
    finally:
        server.close()


def write_codex(
    store: Store, cwd: Path, title: str, messages: list[Message]
) -> Session:
    store.root.mkdir(parents=True, exist_ok=True)
    # The native importer accepts Claude JSONL under the runtime home's .claude/projects.
    # Staging a unique transcript lets Codex own all rollout/index/history writes.
    source_root = (
        store.root.parent / ".claude"
        if store.name.endswith(":sandbox")
        else Path.home() / ".claude"
    )
    projects = source_root / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="agent-session-", dir=projects
    ) as directory:
        staged = write_claude(
            Store("claude:host", Path(directory)),
            cwd,
            title,
            [
                Message(
                    m.role,
                    [
                        text_block(
                            m.text
                            + "\n[Image omitted by Codex session importer]"
                            * sum(b["type"] == "image" for b in m.content)
                        )
                    ],
                    m.timestamp,
                )
                for m in messages
            ],
        )
        source_path = str(staged.path)
        if store.name.endswith(":sandbox"):
            source_path = source_path.replace(str(store.root.parent), "/home/piuser", 1)
        with codex(store, cwd) as server:
            imported = server.call(
                "externalAgentConfig/import",
                {
                    "migrationItems": [
                        {
                            "itemType": "SESSIONS",
                            "description": "Copy selected conversation",
                            "cwd": str(cwd),
                            "details": {
                                "sessions": [
                                    {
                                        "path": source_path,
                                        "cwd": str(cwd),
                                        "title": title,
                                    }
                                ]
                            },
                        }
                    ],
                    "source": "agent-session",
                },
            )
            while True:
                event = server.receive()
                if (
                    event.get("method") == "externalAgentConfig/import/completed"
                    and event["params"]["importId"] == imported["importId"]
                ):
                    results = event["params"]["itemTypeResults"]
                    failures = [f for r in results for f in r.get("failures", [])]
                    successes = [s for r in results for s in r.get("successes", [])]
                    if failures or not successes:
                        raise click.ClickException(
                            f"Codex import failed: {json.dumps(failures)}"
                        )
                    id_ = successes[0]["target"]
                    thread = server.call("thread/read", {"threadId": id_})["thread"]
                    path = str(thread["path"]).replace(
                        "/home/piuser/.codex/", f"{store.root}/", 1
                    )
                    return Session(
                        store, id_, Path(path), cwd, title, datetime.now().timestamp()
                    )


def portable(msg: Message) -> Message:
    images = [b for b in msg.content if b["type"] == "image"]
    for b in msg.content:
        if b["type"] == "tool_result" and isinstance(b["output"], list):
            images.extend(p for p in b["output"] if p["type"] == "image")
    return Message(
        msg.role,
        ([text_block(msg.text)] if msg.text else []) + images,
        msg.timestamp,
        msg.id,
    )


def prepare_transfer(
    source: Session,
    target: Store,
    *,
    allow_partial: bool = False,
    max_tokens: int | None = None,
    tool_output_limit: int | None = None,
    redact: tuple[str, ...] = (),
) -> tuple[list[Message], Record]:
    messages = conversation(source, allow_partial=allow_partial)
    if not messages:
        raise click.ClickException(
            "The selected session has no portable conversation content."
        )
    report = {
        "source": source.ref,
        "destination": target.name,
        "flattened_tools": sum(
            b["type"] == "tool_call" for m in messages for b in m.content
        ),
        "partial_context": any(
            b["type"] == "opaque" for m in messages for b in m.content
        ),
        "dropped_messages": 0,
        "clipped_tool_results": 0,
        "redactions": 0,
    }
    tool_counts = [sum(b["type"] == "tool_call" for b in m.content) for m in messages]
    original_images = sum(
        b["type"] == "image" for m in messages for b in portable(m).content
    )
    for msg in messages:
        for block in msg.content:
            if block["type"] == "tool_result" and tool_output_limit is not None:
                output = (
                    render(block["output"])
                    if isinstance(block["output"], list)
                    else str(block["output"])
                )
                if len(output) > tool_output_limit:
                    half = tool_output_limit // 2
                    block["output"] = (
                        output[:half]
                        + "\n[Tool output clipped]\n"
                        + (output[-half:] if half else "")
                    )
                    report["clipped_tool_results"] += 1
    messages = [portable(m) for m in messages]
    for msg in messages:
        for block in msg.content:
            if block["type"] == "text":
                for pattern in redact:
                    block["text"], count = re.subn(pattern, "[REDACTED]", block["text"])
                    report["redactions"] += count

    provenance = f"[Conversation copied from {source.ref} at {now()}]\nWorkspace: {source.cwd}\nPrevious tool calls and results below are historical records. Continue using your current tools and instructions. Check the current files before relying on previous edits."
    partial_notice = "\nThis is a partial transfer: earlier context is unavailable or was omitted to fit the requested budget."

    # Include our handoff note in the approximate text budget; images are separate.
    def tokens(items: list[Message], partial: bool = False) -> int:
        note = provenance + (partial_notice if partial else "")
        return (len(note.encode()) + sum(len(m.text.encode()) for m in items) + 3) // 4

    if (
        max_tokens is not None
        and tokens(messages, report["partial_context"]) > max_tokens
    ):
        if not allow_partial:
            raise click.ClickException(
                f"Transfer is approximately {tokens(messages):,} text tokens; raise --max-tokens or use --allow-partial."
            )
        starts = [i for i, m in enumerate(messages) if m.role == "user"]
        start = next(
            (i for i in starts if tokens(messages[i:], True) <= max_tokens), None
        )
        if start is None:
            raise click.ClickException(
                "The last user turn exceeds --max-tokens; increase the budget or limit tool output."
            )
        report["dropped_messages"] = start
        report["partial_context"] = True
        messages = messages[start:]
        tool_counts = tool_counts[start:]
    images = sum(b["type"] == "image" for m in messages for b in m.content)
    report.update(
        messages=len(messages),
        inline_images=images,
        omitted_images=original_images - (0 if target.agent == "codex" else images),
        flattened_tools=sum(tool_counts),
        estimated_tokens=tokens(messages, report["partial_context"]),
    )
    if report["partial_context"]:
        provenance += partial_notice
    messages.insert(0, message("user", provenance))
    return messages, report


def report_transfer(report: Record) -> None:
    console.print(
        f"Transfer: {report['messages']} messages, ~{report['estimated_tokens']:,} text tokens; {report['flattened_tools']} tool calls rendered as history; {report['omitted_images']} images omitted.",
        markup=False,
    )
    if report["partial_context"]:
        console.print(
            f"Partial context; {report['dropped_messages']} messages omitted for the budget."
        )
    if report["clipped_tool_results"] or report["redactions"]:
        console.print(
            f"{report['clipped_tool_results']} tool results clipped; {report['redactions']} redactions."
        )


def tag_session(session: Session, source: Session, kind: str) -> Session:
    """Tag only the newly created, closed transcript; the source is never written."""
    data = session.path.read_bytes()
    first, _, rest = data.partition(b"\n")
    row = json.loads(first)
    row.get("payload", row)["agentSession"] = {"parent": source.ref, "kind": kind}
    with tempfile.NamedTemporaryFile(dir=session.path.parent, delete=False) as file:
        file.write(json.dumps(row, ensure_ascii=False).encode() + b"\n" + rest)
    os.replace(file.name, session.path)
    session.parent, session.kind = source.ref, kind
    return session


def fork_session(source: Session, target: Store | None = None) -> Session:
    target = target or source.store
    id_, timestamp = str(uuid4()), now()
    if target.agent == "codex":
        target.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=target.root, prefix="agent-session-fork-"
        ) as directory:
            path = Path(directory) / "source.jsonl"
            write_jsonl(path, list(records(source.path)))
            with codex(target, source.cwd) as server:
                thread = server.call(
                    "thread/fork",
                    {
                        "threadId": source.id,
                        "path": target.runtime_path(path),
                        "deferGoalContinuation": True,
                    },
                )["thread"]
                id_ = thread["id"]
                if source.title:
                    server.call(
                        "thread/name/set", {"threadId": id_, "name": source.title}
                    )
                path = Path(
                    str(thread["path"]).replace(
                        "/home/piuser/.codex/", f"{target.root}/", 1
                    )
                )
    else:
        rows = list(records(source.path))
        if target.agent == "pi":
            rows[0].update(id=id_, timestamp=timestamp, parentSession=str(source.path))
            path = (
                Path(
                    os.environ.get(
                        "PI_CODING_AGENT_SESSION_DIR",
                        target.root / "sessions" / source.path.parent.name,
                    )
                )
                / f"{re.sub(r'[:.]', '-', timestamp)}_{id_}.jsonl"
            )
        else:
            for row in rows:
                row.update(
                    sessionId=id_,
                    forkedFrom={
                        "sessionId": source.id,
                        "messageUuid": row.get("uuid", ""),
                    },
                )
            path = target.root / "projects" / source.path.parent.name / f"{id_}.jsonl"
        write_jsonl(path, rows)
    return tag_session(
        Session(target, id_, path, source.cwd, source.title, path.stat().st_mtime),
        source,
        "fork",
    )


def copy_session(source: Session, target: Store, **options: Any) -> Session:
    if source.store.agent == target.agent:
        return fork_session(source, target)
    messages, report = prepare_transfer(source, target, **options)
    report_transfer(report)
    title = f"{source.title or source.id[:8]} (from {source.store.agent})"
    writers = {"claude": write_claude, "pi": write_pi, "codex": write_codex}
    return tag_session(
        writers[target.agent](target, source.cwd, title, messages),
        source,
        "continuation",
    )


def resolve(reference: str, sessions: list[Session]) -> Session:
    matches = [
        s
        for s in sessions
        if s.ref.startswith(reference)
        or s.id.startswith(reference)
        or f"{s.store.agent}:{s.id}".startswith(reference)
    ]
    if len(matches) != 1:
        raise click.ClickException(
            f"Session reference matches {len(matches)} sessions; use the full agent/store reference."
        )
    return matches[0]


def complete_sessions(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[CompletionItem]:
    return [
        CompletionItem(s.ref, help=s.title)
        for s in discover(Path.cwd().resolve())
        if s.ref.startswith(incomplete)
    ]


def resume_command(session: Session, agent_args: tuple[str, ...] = ()) -> list[str]:
    args = (
        ["--session", session.store.runtime_path(session.path)]
        if session.store.agent == "pi"
        else ["--resume", session.id]
        if session.store.agent == "claude"
        else ["resume", session.id]
    )
    return session.store.command(*args, *agent_args)


def render_resume(session: Session, agent_args: tuple[str, ...] = ()) -> str:
    variable = session.store.variable
    value = session.store.environment().get(variable)
    env = [f"{variable}={value}"] if value is not None else ["-u", variable]
    if session.store.agent == "pi" and "PI_CODING_AGENT_SESSION_DIR" in os.environ:
        env.append(
            f"PI_CODING_AGENT_SESSION_DIR={os.environ['PI_CODING_AGENT_SESSION_DIR']}"
        )
    return f"cd -- {shlex.quote(str(session.cwd))} && " + shlex.join(
        ["env", *env, *resume_command(session, agent_args)]
    )


def resume_session(session: Session, agent_args: tuple[str, ...] = ()) -> None:
    if not session.cwd.is_dir():
        raise click.ClickException(f"Session directory no longer exists: {session.cwd}")
    command = resume_command(session, agent_args)
    console.print(shlex.join(command), markup=False)
    subprocess.run(
        command, cwd=session.cwd, env=session.store.environment(), check=True
    )


def browse_options(function: Any) -> Any:
    for option in [
        click.option(
            "--scope",
            type=click.Choice(["directory", "repo", "branch", "all"]),
            default="directory",
            show_default=True,
        ),
        click.option("--agent", type=click.Choice(["claude", "pi", "codex"])),
        click.option("--store", type=click.Choice([s.name for s in stores()])),
    ]:
        function = option(function)
    return function


def group_sessions(sessions: list[Session]) -> list[Session]:
    by_ref = {s.ref: s for s in sessions}
    children: dict[str, list[Session]] = {}
    for s in sessions:
        children.setdefault(s.parent, []).append(s)
    result, seen = [], set()

    def visit(s: Session) -> None:
        if s.ref in seen:
            return
        seen.add(s.ref)
        result.append(s)
        for child in children.get(s.ref, []):
            visit(child)

    # Visiting the root of each newest descendant orders groups by recent activity.
    for session in sessions:
        ancestor, walked = session, set()
        while ancestor.parent in by_ref and ancestor.ref not in walked:
            walked.add(ancestor.ref)
            ancestor = by_ref[ancestor.parent]
        visit(ancestor)
    return result


def find_sessions(
    query: str,
    scope: str,
    agent: str,
    store: str,
    limit: int = 50,
    *,
    refresh: bool = True,
) -> list[Record]:
    from scripts.agent_session_index import Index, scoped

    with Index() as index:
        if refresh:
            index.refresh()
        sessions, text = scoped(index.sessions(), scope, agent, store, query)
        return index.search(
            text, group_sessions(sessions) if not text else sessions, limit
        )


def picker_rows(rows: list[Record]) -> str:
    return "\n".join(
        f"{r['ref']}\t{r.get('match_line') if r.get('match_line') is not None else -1}\t"
        + " ".join(
            f"{datetime.fromtimestamp(r['updated']):%m-%d %H:%M} {r['store']} {r['title']}"
            f"  {r['branch']} {r['cwd']}"
            f"{'  ↳ ' + r['kind'] + ' of ' + r['parent'] if r['parent'] else ''}"
            f"  {r.get('snippet', '')}".split()
        )
        for r in rows
    )


def pick_session(scope: str, agent: str, store: str, query: str) -> Session | None:
    if not shutil.which("fzf"):
        raise click.ClickException(
            "Install fzf to use the session picker; list/search/show work without it."
        )
    rows = find_sessions(query, scope, agent, store, 10000)
    launcher = shlex.join([sys.executable, "-m", "scripts.agent_session"])

    with tempfile.TemporaryDirectory(prefix="agent-session-picker-") as directory:
        scope_file = Path(directory) / "scope"
        scope_file.write_text(scope)
        args = [
            sys.executable,
            "-m",
            "scripts.agent_session",
            "_rows",
            "--scope-file",
            str(scope_file),
        ]
        if agent:
            args.extend(["--agent", agent])
        if store:
            args.extend(["--store", store])
        reload = shlex.join(args) + " --query={q}"
        bindings = [f"change:reload({reload})"]
        for key, mode in [
            ("ctrl-d", "directory"),
            ("ctrl-g", "repo"),
            ("ctrl-b", "branch"),
            ("ctrl-a", "all"),
        ]:
            change = f"printf %s {mode} > {shlex.quote(str(scope_file))}"
            bindings.append(
                f"{key}:execute-silent({change})+change-prompt({mode}> )+reload({reload})"
            )
        result = subprocess.run(
            [
                "fzf",
                "--disabled",
                "--no-sort",
                "--delimiter=\\t",
                "--with-nth=3..",
                "--query",
                query,
                "--prompt",
                f"{scope}> ",
                "--header",
                "ctrl-d directory · ctrl-g repository · ctrl-b branch · ctrl-a all · agent:/store:/b:/m: filters",
                "--preview",
                f"{launcher} _preview {{1}} --line {{2}}",
                "--preview-window=right:55%:wrap",
                "--bind",
                ",".join(bindings),
            ],
            input=picker_rows(rows),
            text=True,
            stdout=subprocess.PIPE,
        )
    if result.returncode in {1, 130}:
        return None
    result.check_returncode()
    from scripts.agent_session_index import Index

    with Index() as index:
        return resolve(result.stdout.split("\t")[0], index.sessions())


@click.group(invoke_without_command=True)
@browse_options
@click.option("--query", default="", help="Search conversation text and tool inputs.")
@click.option(
    "--print",
    "print_command",
    is_flag=True,
    help="Pick a session and print its resume command.",
)
@click.pass_context
def main(
    ctx: click.Context,
    scope: str,
    agent: str,
    store: str,
    query: str,
    print_command: bool,
) -> None:
    """Search, inspect, fork and continue local agent sessions."""
    if ctx.invoked_subcommand is not None:
        return
    chosen = pick_session(scope, agent, store, query)
    if chosen is None:
        return
    if print_command:
        click.echo(render_resume(chosen))
        return
    while True:
        action = questionary.select(
            "Action", choices=["Resume", "Preview", "Fork", "Copy", "Copy and resume"]
        ).ask()
        if action is None:
            return
        if action == "Preview":
            show_session(chosen)
            continue
        if action == "Resume":
            resume_session(chosen)
        elif action == "Fork":
            copied = fork_session(chosen)
            report_copy(copied)
            resume_session(copied)
        else:
            target = questionary.select(
                "Copy to",
                choices=[questionary.Choice(s.name, value=s) for s in stores()],
            ).ask()
            if target:
                copied = copy_session(chosen, target)
                report_copy(copied)
                if action == "Copy and resume":
                    resume_session(copied)
        return


@main.command("_rows", hidden=True)
@browse_options
@click.option("--query", default="")
@click.option("--scope-file", type=click.Path(path_type=Path))
def rows_command(
    scope: str, agent: str, store: str, query: str, scope_file: Path | None
) -> None:
    if scope_file:
        scope = scope_file.read_text()
    click.echo(
        picker_rows(find_sessions(query, scope, agent, store, 10000, refresh=False))
    )


@main.command("_preview", hidden=True)
@click.argument("session")
@click.option("--line", default=-1, type=int)
def preview_command(session: str, line: int) -> None:
    from scripts.agent_session_index import Index

    with Index() as index:
        selected = resolve(session, index.sessions())
    console.print(selected.title, selected.ref, str(selected.cwd), markup=False)
    for label, text in [
        ("First prompt", selected.first_prompt),
        ("Latest reply", selected.last_reply),
    ]:
        console.rule(label)
        console.print(text, markup=False)
    show_session(selected, match_line=line if line >= 0 else None, chars=12000)


def print_sessions(rows: list[Record], as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False))
        return
    table = Table("Session", "Updated", "Title", "Branch", "Directory")
    for r in rows:
        title = r["title"] + (
            f" (↳ {r['kind']} of {r['parent']})" if r["parent"] else ""
        )
        table.add_row(
            *map(
                Text,
                [
                    r["ref"],
                    f"{datetime.fromtimestamp(r['updated']):%Y-%m-%d %H:%M}",
                    title,
                    r["branch"],
                    r["cwd"],
                ],
            )
        )
        if r.get("match_line") is not None:
            table.add_row("", "", Text(r["snippet"]), "", "")
    console.print(table)


@main.command("list")
@browse_options
@click.option(
    "--all", "all_dirs", is_flag=True, help="Include sessions from every directory."
)
@click.option("--limit", type=click.IntRange(1), default=100)
@click.option("--json", "as_json", is_flag=True)
def list_sessions(
    scope: str, agent: str, store: str, all_dirs: bool, limit: int, as_json: bool
) -> None:
    """List sessions and group their forks/continuations, newest groups first."""
    print_sessions(
        find_sessions("", "all" if all_dirs else scope, agent, store, limit), as_json
    )


@main.command()
@click.argument("query", nargs=-1, required=True)
@browse_options
@click.option("--limit", type=click.IntRange(1), default=50)
@click.option("--json", "as_json", is_flag=True)
def search(
    query: tuple[str, ...],
    scope: str,
    agent: str,
    store: str,
    limit: int,
    as_json: bool,
) -> None:
    """Search titles, conversation text, tool inputs and recorded metadata."""
    print_sessions(find_sessions(" ".join(query), scope, agent, store, limit), as_json)


@main.command("reindex")
def reindex() -> None:
    """Rebuild the disposable local index from native transcripts."""
    from scripts.agent_session_index import Index

    with Index() as index:
        index.refresh(rebuild=True)
        console.print(f"Indexed {len(index.sessions())} sessions.")


def message_page(
    messages: list[Message],
    start: int = 0,
    limit: int = 20,
    offset: int = 0,
    chars: int = 16000,
    tools: bool = False,
) -> Record:
    start = max(0, len(messages) + start) if start < 0 else start
    page = []
    next_page = None
    remaining = chars
    for number in range(start, min(start + limit, len(messages))):
        msg = messages[number]
        text = render(msg.content, folded=not tools)
        window = text[offset : offset + remaining]
        page.append(
            {
                "number": number,
                "line": msg.line,
                "id": msg.id,
                "role": msg.role,
                "timestamp": msg.timestamp,
                "text": window,
                "offset": offset,
                "total_chars": len(text),
                "blocks": [
                    {
                        k: b[k]
                        for k in ("type", "id", "name", "error", "mimeType")
                        if k in b
                    }
                    for b in msg.content
                ],
            }
        )
        remaining -= len(window)
        if offset + len(window) < len(text):
            next_page = {"start": number, "offset": offset + len(window)}
            break
        if number + 1 < len(messages):
            next_page = {"start": number + 1, "offset": 0}
        else:
            next_page = None
        if remaining <= 0:
            break
        offset = 0
    return {"total_messages": len(messages), "messages": page, "next": next_page}


def show_session(
    session: Session,
    *,
    context: bool = False,
    start: int = 0,
    limit: int = 20,
    offset: int = 0,
    chars: int = 16000,
    as_json: bool = False,
    tools: bool = False,
    match_line: int | None = None,
) -> None:
    messages = conversation(session, context=context)
    if match_line is not None:
        start = max(
            0, next((i for i, m in enumerate(messages) if m.line >= match_line), 0) - 2
        )
    page = message_page(messages, start, limit, offset, chars, tools)
    if as_json:
        click.echo(json.dumps({"session": session.data(), **page}, ensure_ascii=False))
        return
    console.print(session.ref, str(session.cwd), markup=False)
    for msg in page["messages"]:
        console.rule(f"{msg['number']} · {msg['role']}")
        console.print(msg["text"], markup=False)
        images = sum(b["type"] == "image" for b in msg["blocks"])
        if images:
            console.print(f"[{images} inline image(s)]", markup=False)
    if page["next"]:
        console.print(
            f"Continue: agent-session show {session.ref} --start {page['next']['start']} --offset {page['next']['offset']}",
            markup=False,
        )


@main.command()
@click.argument("session", shell_complete=complete_sessions)
@click.option(
    "--context",
    is_flag=True,
    help="Show transferable active context instead of full history.",
)
@click.option(
    "--start",
    type=int,
    default=0,
    help="Message index; negative numbers count from the end.",
)
@click.option("--limit", type=click.IntRange(1), default=20)
@click.option(
    "--offset",
    type=click.IntRange(0),
    default=0,
    help="Character offset in the first message.",
)
@click.option(
    "--chars",
    type=click.IntRange(1),
    default=16000,
    help="Maximum text characters per page.",
)
@click.option(
    "--tools", is_flag=True, help="Expand historical tool inputs and outputs."
)
@click.option(
    "--match-line", type=int, help="Open around a search result's match_line."
)
@click.option("--json", "as_json", is_flag=True)
def show(session: str, **options: Any) -> None:
    """Read full history, including messages before compaction and abandoned branches."""
    show_session(resolve(session, discover(None)), **options)


@main.command()
@click.argument("session", shell_complete=complete_sessions)
@click.argument("agent_args", nargs=-1, type=click.UNPROCESSED)
@click.option(
    "--print",
    "print_command",
    is_flag=True,
    help="Print a shell command including cwd and store environment.",
)
def resume(session: str, agent_args: tuple[str, ...], print_command: bool) -> None:
    """Resume with the original agent and store. Pass agent options after --."""
    selected = resolve(session, discover(None))
    if print_command:
        click.echo(render_resume(selected, agent_args))
    else:
        resume_session(selected, agent_args)


def report_copy(session: Session) -> None:
    console.print(f"Created {session.ref}\n{session.path}", markup=False)
    console.print(f"Resume: agent-session resume {session.ref}", markup=False)


@main.command("fork")
@click.argument("session", shell_complete=complete_sessions)
@click.argument("agent_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--resume", "launch", is_flag=True)
@click.option("--dry-run", is_flag=True)
def fork_command(
    session: str, agent_args: tuple[str, ...], launch: bool, dry_run: bool
) -> None:
    """Fork native history in its own agent, preserving tools, images and compactions."""
    if agent_args and not launch:
        raise click.UsageError("Agent arguments require --resume.")
    source = resolve(session, discover(None))
    if dry_run:
        console.print(
            f"Fork {source.ref} in {source.store.name}; preserve native records.",
            markup=False,
        )
        return
    copied = fork_session(source)
    report_copy(copied)
    if launch:
        resume_session(copied, agent_args)


@main.command("copy")
@click.argument("session", shell_complete=complete_sessions)
@click.argument("agent_args", nargs=-1, type=click.UNPROCESSED)
@click.option(
    "--to",
    "destination",
    required=True,
    type=click.Choice(
        [
            "claude",
            "claude:host",
            "claude:sandbox",
            "pi",
            "codex",
            "codex:host",
            "codex:sandbox",
        ]
    ),
)
@click.option("--resume", "launch", is_flag=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report transfer size and losses without creating a session.",
)
@click.option(
    "--allow-partial",
    is_flag=True,
    help="Permit readable context after opaque compaction and omit older turns to fit the budget.",
)
@click.option(
    "--max-tokens",
    type=click.IntRange(1),
    help="Approximate text token budget, excluding images (unlimited by default).",
)
@click.option(
    "--tool-output-limit",
    type=click.IntRange(0),
    help="Clip each tool result to this many characters, keeping both ends.",
)
@click.option(
    "--redact",
    multiple=True,
    help="Replace matches of this regular expression in transferred text.",
)
def copy_command(
    session: str,
    agent_args: tuple[str, ...],
    destination: str,
    launch: bool,
    dry_run: bool,
    **options: Any,
) -> None:
    """Continue in another agent; same-agent copies are native forks."""
    if agent_args and not launch:
        raise click.UsageError("Agent arguments require --resume.")
    destination = (
        destination
        if ":" in destination or destination == "pi"
        else f"{destination}:host"
    )
    target = next(s for s in stores() if s.name == destination)
    source = resolve(session, discover(None))
    defaults = {
        "allow_partial": False,
        "max_tokens": None,
        "tool_output_limit": None,
        "redact": (),
    }
    options = {k: v for k, v in options.items() if v != defaults[k]}
    for pattern in options.get("redact", ()):
        try:
            re.compile(pattern)
        except re.error as error:
            raise click.BadParameter(str(error), param_hint="--redact") from error
    if source.store.agent == target.agent and options:
        raise click.UsageError(
            "Transfer controls apply to cross-agent copies; native forks preserve all records."
        )
    if dry_run:
        if source.store.agent == target.agent:
            console.print(
                f"Fork {source.ref} into {target.name}; preserve native records.",
                markup=False,
            )
        else:
            _, report = prepare_transfer(source, target, **options)
            report_transfer(report)
        return
    copied = copy_session(source, target, **options)
    report_copy(copied)
    if launch:
        resume_session(copied, agent_args)


if __name__ == "__main__":
    main()
