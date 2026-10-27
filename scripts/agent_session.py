"""Browse and copy Claude Code, Pi and Codex conversations between local stores."""

import json
import os
import re
import selectors
import shlex
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import questionary
import rich_click as click
from click.shell_completion import CompletionItem
from rich.console import Console
from rich.table import Table

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
        var = {
            "claude": "CLAUDE_CONFIG_DIR",
            "pi": "PI_CODING_AGENT_DIR",
            "codex": "CODEX_HOME",
        }[self.agent]
        return {**os.environ, var: str(self.root)}


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

    @property
    def ref(self) -> str:
        return f"{self.store.name}:{self.id}"


@dataclass
class Message:
    role: str
    content: list[Record]
    timestamp: str = ""

    @property
    def text(self) -> str:
        return "\n".join(
            block["text"] for block in self.content if block["type"] == "text"
        )


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


def sample(path: Path) -> list[Record]:
    with path.open("rb") as file:
        head = file.read(131072)
        file.seek(max(0, path.stat().st_size - 131072))
        tail = file.read()
    result = []
    for line in (head + b"\n" + tail).splitlines():
        try:
            result.append(json.loads(line))
        except (ValueError, UnicodeDecodeError):
            continue
    return result


def discover(cwd: Path | None) -> list[Session]:
    result = []
    for store in stores():
        databases = sorted(store.root.glob("state_*.sqlite"))
        if store.agent == "codex" and databases:
            with sqlite3.connect(f"{databases[-1].as_uri()}?mode=ro", uri=True) as db:
                for id_, path, directory, title, updated in db.execute(
                    "SELECT id, rollout_path, cwd, COALESCE(name, title), updated_at "
                    "FROM threads WHERE archived=0 AND source NOT LIKE '%subagent%'"
                ):
                    path = str(path).replace(
                        "/home/piuser/.codex/", f"{store.root}/", 1
                    )
                    directory = Path(directory)
                    if cwd is None or directory.resolve() == cwd:
                        result.append(
                            Session(store, id_, Path(path), directory, title, updated)
                        )
            continue
        root = store.root / ("projects" if store.agent == "claude" else "sessions")
        if store.agent == "pi":
            root = Path(
                os.environ.get("PI_CODING_AGENT_SESSION_DIR", root)
            ).expanduser()
        pattern = "*/*.jsonl" if store.agent == "claude" else "**/*.jsonl"
        for path in root.glob(pattern):
            rows = sample(path)
            header = next(
                (
                    r.get("payload", r)
                    for r in rows
                    if r.get("cwd") or r.get("type") == "session_meta"
                ),
                {},
            )
            if not header.get("cwd"):
                continue
            directory = Path(header["cwd"])
            if cwd is not None and directory.resolve() != cwd:
                continue
            title = named = ""
            for row in rows:
                if row.get("type") == "custom-title":
                    named = row["customTitle"]
                if row.get("type") in {"custom-title", "ai-title", "session_info"}:
                    title = (
                        row.get("customTitle")
                        or row.get("aiTitle")
                        or row.get("name")
                        or title
                    )
                message = row.get("message", {})
                if (
                    not title
                    and message.get("role") == "user"
                    and not row.get("isMeta")
                ):
                    title = flatten(message.get("content", ""))[0]
            id_ = header.get("id") or header.get("sessionId") or path.stem
            title = named or title
            result.append(
                Session(
                    store,
                    id_,
                    path,
                    directory,
                    " ".join(title.split())[:120],
                    path.stat().st_mtime,
                )
            )
    return sorted(result, key=lambda session: session.updated, reverse=True)


def flatten(content: Any) -> tuple[str, list[Record]]:
    """Render foreign tools as historical evidence; retain portable inline images."""
    if isinstance(content, str):
        return content, []
    parts, images = [], []
    for block in content or []:
        kind = block.get("type", "")
        if kind in {"text", "Text", "input_text", "output_text"}:
            parts.append(block.get("text", ""))
        elif kind in {"tool_use", "toolCall"}:
            arguments = block.get("input", block.get("arguments", {}))
            parts.append(
                f"[Historical tool call: {block['name']}]\n{json.dumps(arguments, ensure_ascii=False)}"
            )
        elif kind == "tool_result":
            text, nested_images = flatten(block.get("content", ""))
            parts.append(f"[Historical tool result]\n{text}")
            images.extend(nested_images)
        elif kind == "image":
            source = block.get("source", {})
            if source.get("type") == "base64":
                images.append(
                    {
                        "type": "image",
                        "data": source["data"],
                        "mimeType": source["media_type"],
                    }
                )
            elif "data" in block:
                images.append(block)
            else:
                parts.append("[Image omitted: no inline image data]")
        elif kind == "input_image":
            url = block.get("image_url", "")
            if url.startswith("data:") and ";base64," in url:
                media, data = url[5:].split(";base64,", 1)
                images.append({"type": "image", "data": data, "mimeType": media})
            else:
                parts.append("[Image omitted: external image reference]")
        elif kind not in {"thinking", "redacted_thinking"}:
            parts.append(f"[Unsupported content omitted: {kind}]")
    return "\n\n".join(parts), images


def message(role: str, content: Any, timestamp: str = "") -> Message:
    text, images = flatten(content)
    return Message(role, ([text_block(text)] if text else []) + images, timestamp)


def branch(rows: list[Record], id_key: str, parent_key: str) -> list[Record]:
    by_id = {row[id_key]: row for row in rows if id_key in row}
    path = []
    node = next(reversed(by_id.values()), None)
    seen = set()
    while node and node[id_key] not in seen:
        path.append(node)
        seen.add(node[id_key])
        node = by_id.get(node.get(parent_key))
    return path[::-1]


def read_pi(rows: list[Record]) -> list[Message]:
    path = branch([r for r in rows if r["type"] != "session"], "id", "parentId")
    edits = {
        r["targetId"]: r["replacement"] for r in path if r["type"] == "context_edit"
    }
    compact = next(
        (i for i in reversed(range(len(path))) if path[i]["type"] == "compaction"), None
    )
    if compact is not None:
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
        if row.get("id") in edits:
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
                message("user", f"[Previous context summary]\n{row['summary']}")
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
                        str(row["timestamp"]),
                    )
                )
            elif role == "toolResult":
                converted = message("assistant", msg["content"], str(row["timestamp"]))
                converted.content.insert(
                    0, text_block(f"[Historical tool result: {msg['toolName']}]")
                )
                result.append(converted)
            elif role == "bashExecution" and not msg.get("excludeFromContext"):
                result.append(
                    message(
                        "assistant",
                        f"[Historical shell command]\n{msg['command']}\n{msg['output']}",
                    )
                )
    return result


def read_claude(rows: list[Record]) -> list[Message]:
    rows = [r for r in rows if not r.get("isSidechain")]
    path = branch(rows, "uuid", "parentUuid")
    by_id = {r["uuid"]: r for r in rows if "uuid" in r}
    # Claude reconnects preserved pre-compaction messages after its summary in memory.
    for row in path[:]:
        if row.get("subtype") == "compact_boundary":
            preserved = row.get("compactMetadata", {}).get("preservedMessages", {})
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
                path[anchor + 1 : anchor + 1] = [
                    by_id[id_]
                    for id_ in preserved.get("allUuids", preserved.get("uuids", []))
                    if id_ in by_id and id_ not in existing
                ]
    return [
        message(
            "assistant"
            if isinstance(r["message"]["content"], list)
            and r["message"]["content"]
            and all(b.get("type") == "tool_result" for b in r["message"]["content"])
            else r["type"],
            r["message"]["content"],
            r.get("timestamp", ""),
        )
        for r in path
        if r["type"] in {"user", "assistant"}
        and (not r.get("isMeta") or r.get("isCompactSummary"))
    ]


def read_codex(rows: list[Record]) -> list[Message]:
    start = next(
        (i for i in reversed(range(len(rows))) if rows[i]["type"] == "compacted"), 0
    )
    rows = rows[start:]
    result = []
    has_user_events = any(
        r.get("type") == "event_msg"
        and (
            r["payload"].get("type") == "user_message"
            or r["payload"].get("item", {}).get("type") == "UserMessage"
        )
        for r in rows
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
                    f"[Historical tool call: {item.get('name', 'tool')}]\n{item.get('arguments', item.get('input', ''))}",
                    timestamp,
                )
            )
        elif kind in {"function_call_output", "custom_tool_call_output"}:
            output = item.get("output", "")
            converted = message(
                "assistant",
                output if isinstance(output, (str, list)) else json.dumps(output),
                timestamp,
            )
            converted.content.insert(0, text_block("[Historical tool result]"))
            result.append(converted)
        elif kind in {"compaction", "context_compaction"}:
            raise click.ClickException(
                "This Codex context contains an opaque compaction; its encrypted state cannot be transferred."
            )

    for row in rows:
        data, timestamp = row.get("payload", {}), row.get("timestamp", "")
        if row["type"] == "compacted":
            result.clear()
            if data.get("replacement_history") is not None:
                for item in data["replacement_history"]:
                    append(item, timestamp, checkpoint=True)
            elif data.get("message"):
                result.append(
                    message(
                        "user",
                        f"[Previous context summary]\n{data['message']}",
                        timestamp,
                    )
                )
            else:
                raise click.ClickException(
                    "This Codex compaction has no portable summary."
                )
        elif row["type"] == "response_item":
            append(data, timestamp)
        elif row["type"] == "event_msg":
            item = data.get("item", {})
            if data.get("type") == "user_message":
                result.append(message("user", data["message"], timestamp))
            elif item.get("type") == "UserMessage":
                result.append(message("user", item["content"], timestamp))
    return result


def conversation(session: Session) -> list[Message]:
    readers = {"pi": read_pi, "claude": read_claude, "codex": read_codex}
    return [
        m
        for m in readers[session.store.agent](list(records(session.path)))
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


def copy_session(source: Session, target: Store) -> Session:
    messages = conversation(source)
    if not messages:
        raise click.ClickException(
            "The selected session has no portable conversation content."
        )
    provenance = f"[Conversation copied from {source.ref} at {now()}]\nWorkspace: {source.cwd}\nPrevious tool calls and results below are historical records. Continue using your current tools and instructions."
    messages.insert(0, message("user", provenance))
    images = sum(b["type"] == "image" for m in messages for b in m.content)
    if target.agent == "codex" and images:
        console.print(
            f"Codex import replaces {images} inline image(s) with omission notices."
        )
    title = f"{source.title or source.id[:8]} (from {source.store.agent})"
    writers = {"claude": write_claude, "pi": write_pi, "codex": write_codex}
    return writers[target.agent](target, source.cwd, title, messages)


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


def resume_session(session: Session) -> None:
    args = (
        ["--session", str(session.path)]
        if session.store.agent == "pi"
        else ["--resume", session.id]
        if session.store.agent == "claude"
        else ["resume", session.id]
    )
    command = session.store.command(*args)
    console.print(shlex.join(command), markup=False)
    subprocess.run(
        command, cwd=session.cwd, env=session.store.environment(), check=True
    )


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Browse and copy agent sessions for the current directory."""
    if ctx.invoked_subcommand is not None:
        return
    sessions = discover(Path.cwd().resolve())
    if not sessions:
        console.print("No sessions for this directory.")
        return
    chosen = questionary.select(
        "Session",
        choices=[
            questionary.Choice(
                f"{s.store.name:16} {datetime.fromtimestamp(s.updated):%Y-%m-%d %H:%M}  {s.title}",
                value=s,
            )
            for s in sessions
        ],
    ).ask()
    if chosen is None:
        return
    action = questionary.select("Action", choices=["Preview", "Resume", "Copy"]).ask()
    if action == "Preview":
        show_session(chosen)
    elif action == "Resume":
        resume_session(chosen)
    elif action == "Copy":
        target = questionary.select(
            "Copy to",
            choices=[
                questionary.Choice(s.name, value=s)
                for s in stores()
                if s != chosen.store
            ],
        ).ask()
        if target:
            report_copy(copy_session(chosen, target))


@main.command("list")
@click.option(
    "--all", "all_dirs", is_flag=True, help="Include sessions from every directory."
)
@click.option(
    "--json", "as_json", is_flag=True, help="Output session metadata as JSON."
)
def list_sessions(all_dirs: bool, as_json: bool) -> None:
    """List sessions, newest first."""
    sessions = discover(None if all_dirs else Path.cwd().resolve())
    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "ref": s.ref,
                        "title": s.title,
                        "cwd": str(s.cwd),
                        "path": str(s.path),
                        "updated": s.updated,
                    }
                    for s in sessions
                ],
                ensure_ascii=False,
            )
        )
        return
    table = Table("Session", "Updated", "Title", *(["Directory"] if all_dirs else []))
    for s in sessions:
        table.add_row(
            f"{s.store.name}:{s.id[:8]}",
            f"{datetime.fromtimestamp(s.updated):%Y-%m-%d %H:%M}",
            s.title,
            *([str(s.cwd)] if all_dirs else []),
        )
    console.print(table)


def show_session(session: Session) -> None:
    console.print(session.ref, str(session.cwd), markup=False)
    for msg in conversation(session):
        console.rule(msg.role)
        console.print(msg.text, markup=False)
        images = sum(b["type"] == "image" for b in msg.content)
        if images:
            console.print(f"[{images} inline image(s)]", markup=False)


@main.command()
@click.argument("session", shell_complete=complete_sessions)
def show(session: str) -> None:
    """Preview the portable conversation context."""
    show_session(resolve(session, discover(None)))


@main.command()
@click.argument("session", shell_complete=complete_sessions)
def resume(session: str) -> None:
    """Resume with the original agent and store."""
    resume_session(resolve(session, discover(None)))


def report_copy(session: Session) -> None:
    console.print(f"Created {session.ref}\n{session.path}", markup=False)
    console.print(f"Resume: agent-session resume {session.ref}", markup=False)


@main.command("copy")
@click.argument("session", shell_complete=complete_sessions)
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
@click.option(
    "--resume", "launch", is_flag=True, help="Resume the copied session immediately."
)
def copy_command(session: str, destination: str, launch: bool) -> None:
    """Copy current conversation context into a new native session."""
    destination = (
        destination
        if ":" in destination or destination == "pi"
        else f"{destination}:host"
    )
    target = next(s for s in stores() if s.name == destination)
    copied = copy_session(resolve(session, discover(None)), target)
    report_copy(copied)
    if launch:
        resume_session(copied)


if __name__ == "__main__":
    main()
