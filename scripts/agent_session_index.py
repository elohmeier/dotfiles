"""Rebuildable metadata and FTS5 index over native agent transcripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from rich.console import Console

from scripts import agent_session as app


@lru_cache(maxsize=1024)
def repository(cwd: Path) -> str:
    if not cwd.is_dir():
        return ""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(cwd),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def current_branch(cwd: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()


def scoped(
    sessions: list[app.Session],
    scope: str,
    agent: str = "",
    store: str = "",
    query: str = "",
) -> tuple[list[app.Session], str]:
    filters = {}
    terms = []
    for token in re.findall(r'"[^"]*"|\S+', query):
        key, _, value = token.partition(":")
        if key in {"agent", "store", "b", "m"}:
            filters[key] = value
        else:
            terms.append(token)
    cwd = Path.cwd().resolve()
    repo = repository(cwd) if scope in {"repo", "branch"} else ""
    branch = current_branch(cwd) if scope == "branch" and repo else ""
    selected = [
        s
        for s in sessions
        if (scope != "directory" or s.cwd.resolve() == cwd)
        and (scope not in {"repo", "branch"} or not repo or s.repo == repo)
        and (not branch or s.branch == branch)
        and (
            not (filters.get("agent") or agent)
            or s.store.agent == (filters.get("agent") or agent)
        )
        and (
            not (filters.get("store") or store)
            or s.store.name == (filters.get("store") or store)
        )
        and (not filters.get("b") or s.branch == filters["b"])
        and (not filters.get("m") or filters["m"].lower() in s.model.lower())
    ]
    return selected, " ".join(terms)


def searchable(content: list[app.Record]) -> str:
    return app.render(
        [b for b in content if b["type"] not in {"image", "tool_result", "opaque"}]
    )


def metadata(meta: app.Record, row: app.Record, store: app.Store) -> None:
    data = row.get("payload", row)
    kind = row.get("type")
    if data.get("cwd"):
        meta["cwd"] = data["cwd"]
    if kind in {"session", "session_meta"}:
        meta["id"] = data.get("id", meta.get("id", ""))
    elif row.get("sessionId"):
        meta["id"] = row["sessionId"]
    link = data.get("agentSession", row.get("agentSession", {}))
    if link:
        meta.update(parent=link["parent"], kind=link["kind"], _linked=True)
    elif not meta.get("_linked") and row.get("forkedFrom"):
        meta.update(
            parent=f"{store.name}:{row['forkedFrom']['sessionId']}", kind="fork"
        )
    elif not meta.get("_linked") and data.get("forked_from_id"):
        meta.update(parent=f"{store.name}:{data['forked_from_id']}", kind="fork")
    elif not meta.get("_linked") and kind == "session" and row.get("parentSession"):
        meta.update(parent_path=row["parentSession"], kind="fork")
    branch = row.get("gitBranch") or (data.get("git") or {}).get("branch")
    model = (
        row.get("message", {}).get("model") or data.get("model") or row.get("modelId")
    )
    if branch:
        meta["branch"] = branch
    if model and model != "imported":
        meta["model"] = model
    titles = meta.setdefault("_titles", {})
    for source, field in [(1, "aiTitle"), (2, "customTitle"), (3, "agentName")]:
        if field in row:
            titles[str(source)] = row[field]
    if kind == "session_info":
        titles["2"] = row.get("name", "")
    named = next((titles[k] for k in sorted(titles, reverse=True) if titles[k]), "")
    meta["title"] = named or meta.get("first_prompt", "")


class Index:
    def __init__(self) -> None:
        cache = (
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            / "agent-session"
        )
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = cache / "index.sqlite"
        path.touch(mode=0o600, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
            self.db.executescript(
                "DROP TABLE IF EXISTS search_fts; DROP TABLE IF EXISTS documents; DROP TABLE IF EXISTS sources; PRAGMA user_version=1;"
            )
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                key TEXT PRIMARY KEY, store TEXT, root TEXT, path TEXT,
                stamp TEXT, offset INTEGER, digest TEXT, meta TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
                source UNINDEXED, position UNINDEXED, title, body
            );
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY, source TEXT, position INTEGER
            );
            CREATE INDEX IF NOT EXISTS documents_source ON documents(source, position);
        """)

    def __enter__(self) -> Index:
        return self

    def __exit__(self, *_: Any) -> None:
        self.db.close()

    def remove(self, source: str, position: int | None = None) -> None:
        clause = "source=?" + (" AND position=?" if position is not None else "")
        params = (source, position) if position is not None else (source,)
        ids = self.db.execute(
            f"SELECT id FROM documents WHERE {clause}", params
        ).fetchall()
        self.db.executemany(
            "DELETE FROM search_fts WHERE rowid=?", [(r[0],) for r in ids]
        )
        self.db.execute(f"DELETE FROM documents WHERE {clause}", params)

    def insert(self, source: str, position: int, title: str, body: str) -> None:
        cursor = self.db.execute(
            "INSERT INTO documents(source, position) VALUES (?, ?)", (source, position)
        )
        self.db.execute(
            "INSERT INTO search_fts(rowid, source, position, title, body) VALUES (?, ?, ?, ?, ?)",
            (cursor.lastrowid, source, position, title, body),
        )

    def refresh(self, *, rebuild: bool = False) -> None:
        with Console(stderr=True).status("Refreshing agent sessions…"), self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if rebuild:
                self.db.execute("DELETE FROM sources")
                self.db.execute("DELETE FROM search_fts")
                self.db.execute("DELETE FROM documents")
            seen = set()
            for store, path, overrides in app.candidates():
                key = f"{store.name}:{path}"
                seen.add(key)
                self.update(key, store, path, overrides)
            for row in self.db.execute("SELECT key FROM sources").fetchall():
                if row["key"] not in seen:
                    self.db.execute("DELETE FROM sources WHERE key=?", (row["key"],))
                    self.remove(row["key"])

    def update(
        self, key: str, store: app.Store, path: Path, overrides: app.Record
    ) -> None:
        old = self.db.execute("SELECT * FROM sources WHERE key=?", (key,)).fetchone()
        stat = path.stat() if path.exists() else None
        stamp = (
            json.dumps([stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size])
            if stat
            else ""
        )
        meta = json.loads(old["meta"]) if old else {}
        if old and old["stamp"] == stamp and meta.get("_overrides", {}) == overrides:
            return
        offset = old["offset"] if old else 0
        digest = ""
        rows = []
        if stat:
            with path.open("rb") as file:
                if old and offset:
                    previous = json.loads(old["stamp"]) if old["stamp"] else []
                    file.seek(max(0, offset - 4096))
                    boundary = hashlib.sha256(file.read(min(4096, offset))).hexdigest()
                    if (
                        previous[:2] != [stat.st_dev, stat.st_ino]
                        or stat.st_size <= previous[3]
                        or boundary != old["digest"]
                    ):
                        offset = 0
                if not offset:
                    meta = {}
                    self.remove(key)
                file.seek(offset)
                while line := file.readline():
                    if not line.endswith(b"\n"):
                        break
                    offset = file.tell()
                    try:
                        rows.append(json.loads(line))
                    except (ValueError, UnicodeDecodeError):
                        continue
                file.seek(max(0, offset - 4096))
                digest = hashlib.sha256(file.read(min(4096, offset))).hexdigest()
        elif old:
            self.remove(key)
            meta = {}
        meta.setdefault("id", path.stem)
        meta.setdefault("updated", stat.st_mtime if stat else 0)
        if stat:
            meta["updated"] = stat.st_mtime
        has_events = meta.get("_user_events", False) or any(
            r.get("type") == "event_msg"
            and (
                r.get("payload", {}).get("type") == "user_message"
                or r.get("payload", {}).get("item", {}).get("type") == "UserMessage"
            )
            for r in rows
        )
        # New canonical user events supersede response-item copies, including older pages.
        if (
            has_events
            and not meta.get("_user_events")
            and old
            and old["offset"]
            and rows
        ):
            self.db.execute("DELETE FROM sources WHERE key=?", (key,))
            self.remove(key)
            self.update(key, store, path, overrides)
            return
        reader = {
            "pi": app.read_pi,
            "claude": app.read_claude,
            "codex": app.read_codex,
        }[store.agent]
        for row in rows:
            position = meta.get("_lines", 0)
            meta["_lines"] = position + 1
            metadata(meta, row, store)
            messages = reader(
                [row],
                context=False,
                **({"user_events": has_events} if store.agent == "codex" else {}),
            )
            for msg in messages:
                body = searchable(msg.content)
                self.insert(key, position, "", body)
                meta["message_count"] = meta.get("message_count", 0) + 1
                text = "\n".join(b["text"] for b in msg.content if b["type"] == "text")
                if msg.role == "user" and text and not meta.get("first_prompt"):
                    meta["first_prompt"] = text[:1000]
                elif msg.role == "assistant" and text:
                    meta["last_reply"] = text[:1000]
        meta["_user_events"] = has_events
        meta["_overrides"] = overrides
        meta.update(overrides)
        meta["title"] = " ".join(
            (meta.get("title") or meta.get("first_prompt", "")).split()
        )[:120]
        if meta.get("cwd"):
            meta["repo"] = repository(Path(meta["cwd"]).resolve())
        self.remove(key, -1)
        self.insert(
            key,
            -1,
            meta["title"],
            " ".join(str(meta.get(k, "")) for k in ["cwd", "branch", "model"]),
        )
        self.db.execute(
            "INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                store.name,
                str(store.root),
                str(path),
                stamp,
                offset,
                digest,
                json.dumps(meta),
            ),
        )

    def sessions(self) -> list[app.Session]:
        sessions = []
        parents = {}
        for row in self.db.execute("SELECT * FROM sources"):
            meta = json.loads(row["meta"])
            if not meta.get("cwd"):
                continue
            session = app.Session(
                app.Store(row["store"], Path(row["root"])),
                meta["id"],
                Path(row["path"]),
                Path(meta["cwd"]),
                meta["title"],
                meta["updated"],
                **{
                    k: meta[k]
                    for k in [
                        "branch",
                        "model",
                        "repo",
                        "parent",
                        "kind",
                        "message_count",
                        "first_prompt",
                        "last_reply",
                    ]
                    if k in meta
                },
            )
            sessions.append(session)
            if meta.get("parent_path"):
                parents[session.ref] = meta["parent_path"]
        by_path = {str(s.path): s.ref for s in sessions}
        for session in sessions:
            if not session.parent:
                session.parent = by_path.get(parents.get(session.ref, ""), "")
        return sorted(sessions, key=lambda s: s.updated, reverse=True)

    def search(
        self, query: str, sessions: list[app.Session], limit: int = 50
    ) -> list[app.Record]:
        by_path = {f"{s.store.name}:{s.path}": s for s in sessions}
        tokens = re.findall(r'"([^"]*)"|(\S+)', query)
        terms = [a or b for a, b in tokens if a or b]
        if not terms:
            return [
                {
                    **s.data(),
                    "match_line": None,
                    "snippet": s.last_reply or s.first_prompt,
                }
                for s in sessions[:limit]
            ]
        expression = " AND ".join(
            '"'
            + t.replace('"', '""')
            + '"'
            + ("*" if i == len(terms) - 1 and len(t) >= 2 and not tokens[i][0] else "")
            for i, t in enumerate(terms)
        )
        result = []
        seen = set()
        for row in self.db.execute(
            "SELECT source, position, snippet(search_fts, 3, '[', ']', ' … ', 28) AS snippet FROM search_fts WHERE search_fts MATCH ? ORDER BY bm25(search_fts, 0, 0, 5, 1)",
            (expression,),
        ):
            session = by_path.get(row["source"])
            if session and session.ref not in seen:
                result.append(
                    {
                        **session.data(),
                        "match_line": row["position"] if row["position"] >= 0 else None,
                        "snippet": row["snippet"] or session.title,
                    }
                )
                seen.add(session.ref)
                if len(result) == limit:
                    break
        return result
