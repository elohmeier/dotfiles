"""JSON API and static UI for browsing agent sessions in a web browser."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from flask import Flask, abort, request, send_from_directory

from scripts import agent_session as app
from scripts.agent_session_index import Index, scoped

UI = Path(__file__).with_name("agent_session_ui")
CLIP = 4000
lock = threading.Lock()
refreshed = 0.0


def sessions() -> list[app.Session]:
    global refreshed
    with lock, Index() as index:
        if time.monotonic() - refreshed > 20:
            index.refresh()
            refreshed = time.monotonic()
        return index.sessions()


def workspace(session: app.Session) -> str:
    return str(Path(session.repo).parent) if session.repo else str(session.cwd)


def row(session: app.Session, **extra: Any) -> app.Record:
    return {
        **session.data(),
        "agent": session.store.agent,
        "workspace": workspace(session),
        "cwd_exists": session.cwd.is_dir(),
        "resume": app.render_resume(session),
        **extra,
    }


def clip(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) <= CLIP:
        return text
    half = CLIP // 2
    return f"{text[:half]}\n… {len(text) - CLIP} characters omitted …\n{text[-half:]}"


def transcript(messages: list[app.Message]) -> list[app.Record]:
    items: list[app.Record] = []
    tools: dict[str, app.Record] = {}
    for number, msg in enumerate(messages):
        blocks = []
        for b in msg.content:
            kind = b["type"]
            if kind == "tool_call":
                tool = {"type": "tool", "name": b["name"], "input": clip(b["input"])}
                tools[b.get("id") or str(id(b))] = tool
                blocks.append(tool)
            elif kind == "tool_result":
                output = b["output"]
                result = clip(
                    app.render(output) if isinstance(output, list) else output
                )
                if tool := tools.get(b.get("id", "")):
                    tool.update(output=result, error=b.get("error", False))
                else:
                    blocks.append(
                        {
                            "type": "tool",
                            "name": b.get("name", "result"),
                            "input": "",
                            "output": result,
                            "error": b.get("error", False),
                        }
                    )
            elif kind == "image":
                blocks.append({"type": "image", "mimeType": b.get("mimeType", "")})
            elif kind in {"text", "summary"} and b.get("text", "").strip():
                blocks.append({"type": kind, "text": b["text"]})
        if not blocks:
            continue
        previous = items[-1] if items else None
        if previous and previous["role"] == msg.role == "assistant":
            previous["blocks"] += blocks
            previous["line_end"] = msg.line
            continue
        items.append(
            {
                "id": f"m{number}",
                "role": msg.role,
                "timestamp": msg.timestamp,
                "line": msg.line,
                "line_end": msg.line,
                "blocks": blocks,
            }
        )
    return items


def create() -> Flask:
    web = Flask(__name__, static_folder=None)

    @web.get("/api/sessions")
    def list_sessions() -> Any:
        args = request.args
        selected, text = scoped(
            sessions(),
            "all",
            args.get("agent", ""),
            args.get("store", ""),
            args.get("q", ""),
        )
        selected = [
            s
            for s in selected
            if (not args.get("workspace") or workspace(s) == args["workspace"])
            and (not args.get("cwd") or str(s.cwd) == args["cwd"])
            and (not args.get("branch") or s.branch == args["branch"])
        ]
        by_ref = {s.ref: s for s in selected}
        limit = int(args.get("limit", 300))
        recent = text and args.get("sort") == "recent"
        with Index() as index:
            results = index.search(
                text,
                selected if text else app.group_sessions(selected),
                len(selected) if recent else limit,
                ("\x02", "\x03"),
            )
        if recent:
            results = sorted(results, key=lambda r: r["updated"], reverse=True)[:limit]
        return [
            row(by_ref[r["ref"]], snippet=r["snippet"], match_line=r["match_line"])
            for r in results
        ]

    @web.get("/api/workspaces")
    def workspaces() -> Any:
        groups: dict[str, list[app.Session]] = {}
        for s in sessions():
            groups.setdefault(workspace(s), []).append(s)
        result: list[app.Record] = []
        for key, members in groups.items():
            cwds: dict[str, list[app.Session]] = {}
            for s in members:
                cwds.setdefault(str(s.cwd), []).append(s)
            roots = [s for s in members if not s.parent] or members
            result.append(
                {
                    "key": key,
                    "name": Path(key).name,
                    "exists": Path(key).is_dir(),
                    "count": len(members),
                    "updated": members[0].updated,
                    "branches": sorted({s.branch for s in members if s.branch}),
                    "cwds": [
                        {"cwd": c, "count": len(v), "updated": v[0].updated}
                        for c, v in cwds.items()
                    ],
                    "latest": row(roots[0]),
                }
            )
        return sorted(result, key=lambda w: w["updated"], reverse=True)

    @web.get("/api/session")
    def show() -> Any:
        found = [s for s in sessions() if s.ref == request.args.get("ref")]
        if not found:
            abort(404)
        session = found[0]
        items = transcript(app.conversation(session, context=False))
        line = request.args.get("line", type=int)
        focus = next(
            (i["id"] for i in items if line is not None and i["line_end"] >= line), None
        )
        return {
            "session": row(session),
            "focus": focus,
            "messages": items,
        }

    @web.get("/")
    @web.get("/<path:path>")
    def static(path: str = "") -> Any:
        if path and (UI / path).is_file():
            return send_from_directory(UI, path)
        return send_from_directory(UI, "index.html")

    return web


def serve(host: str, port: int) -> None:
    from waitress import serve as run

    app.console.print(f"Serving agent sessions on http://{host}:{port}")
    run(create(), host=host, port=port, threads=8)
