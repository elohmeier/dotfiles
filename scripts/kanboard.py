"""Inspect and change Kanboard boards and tasks through its JSON-RPC API.

Prints JSON by default (-o jsonl or -o table for other formats). Projects take
an identifier, name or ID; columns, swimlanes, users and tags take names or IDs.

Acts as KANBOARD_USER with a personal API token (Kanboard: My profile > API):
KANBOARD_TOKEN, KANBOARD_TOKEN_COMMAND, or the host credential stored with
`secret-entry request --host KANBOARD_TOKEN` (macOS Keychain or Linux TPM2).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from functools import cached_property

import click
import httpx
from rich.console import Console
from rich.table import Table

from scripts.secret_entry import SecretError, host_secret, host_storage

DEFAULT_URL = "https://kanboard-api.pug-coho.ts.net/jsonrpc.php"
DEFAULT_WEB = "https://violet-ridge-anchor.hf40.de"
DEFAULT_USER = "enno"
STATUS = {"open": "status:open", "closed": "status:closed", "all": ""}
# Columns of -o table, in order; JSON output has every field.
TABLE = (
    *("id", "identifier", "date", "title", "name", "field", "value", "label"),
    *("column", "swimlane", "status", "assignee", "author", "role", "tags"),
    *("due", "event", "position", "active", "open", "task_id", "text"),
)
SUBTASK_STATUS = {0: "todo", 1: "in progress", 2: "done"}


class Error(click.ClickException):
    """Reported as {"error": ...} on stderr."""

    exit_code = 1

    def show(self, file=None) -> None:
        click.echo(json.dumps({"error": self.message}), err=True)


class NotFound(Error):
    exit_code = 3


class ApiError(Error):
    exit_code = 4


def token() -> str:
    value = os.getenv("KANBOARD_TOKEN")
    if not value and (command := os.getenv("KANBOARD_TOKEN_COMMAND")):
        result = subprocess.run(
            shlex.split(command), capture_output=True, text=True, check=False
        )
        if result.returncode:
            raise Error("KANBOARD_TOKEN_COMMAND failed")
        value = result.stdout
    if not value:
        try:
            value = host_secret("KANBOARD_TOKEN")
        except SecretError as error:
            raise Error(str(error)) from None
    if not value:
        try:
            host_storage()
            setup = "run `secret-entry request --host KANBOARD_TOKEN` in your terminal"
        except SecretError:
            setup = (
                "set KANBOARD_TOKEN or KANBOARD_TOKEN_COMMAND to read it from your "
                "password manager (e.g. 'pass show kanboard/token')"
            )
        raise Error(
            f"no token: create a personal API token under My profile > API, then {setup}"
        )
    return value.strip()


def timestamp(value) -> str | None:
    if not value or not str(value).isdigit() or int(value) == 0:
        return None
    return (
        datetime.fromtimestamp(int(value), UTC).astimezone().isoformat("T", "seconds")
    )


def number(value) -> int | None:
    return int(value) if value not in (None, "") else None


def text(value: str | None) -> str | None:
    """`-` reads stdin, `@path` reads a file, anything else is literal."""
    if value == "-":
        return sys.stdin.read()
    if value and value.startswith("@"):
        with open(value[1:]) as f:
            return f.read()
    return value


class Kanboard:
    def __init__(self, url: str, user: str, web: str):
        self.url, self.user, self.web = url, user, web.rstrip("/")

    @cached_property
    def http(self) -> httpx.Client:
        return httpx.Client(auth=(self.user, token()), timeout=30)

    def batch(self, calls: list[tuple[str, dict]]) -> list:
        if not calls:
            return []
        body = [
            {"jsonrpc": "2.0", "id": i, "method": m, "params": p}
            for i, (m, p) in enumerate(calls)
        ]
        response = self.http.post(self.url, json=body)
        if response.status_code == 401:
            raise ApiError(f"authentication failed for {self.user}")
        if response.is_error:
            raise ApiError(f"HTTP {response.status_code}")
        data = response.json()
        data = data if isinstance(data, list) else [data]
        for item in data:
            if "error" in item:
                method = calls[item["id"]][0] if item.get("id") is not None else "call"
                raise ApiError(f"{method}: {item['error'].get('message')}")
        return [item.get("result") for item in sorted(data, key=lambda x: x["id"])]

    def call(self, method: str, **params):
        return self.batch([(method, params)])[0]

    def change(self, method: str, **params):
        """A mutation; Kanboard answers false when it refuses one."""
        result = self.call(method, **params)
        if result is False or result is None:
            raise ApiError(f"{method} was refused")
        return result

    @cached_property
    def me(self) -> dict:
        return self.call("getMe")

    def project(self, ref: str) -> Project:
        if ref.isdigit():
            found = self.call("getProjectById", project_id=int(ref))
        else:
            found = self.call(
                "getProjectByIdentifier", identifier=ref.upper()
            ) or self.call("getProjectByName", name=ref)
        if not found:
            raise NotFound(f"project {ref}")
        return Project(self, found)

    def task_project(self, task_id: int) -> Project:
        task = self.call("getTask", task_id=task_id)
        if not task:
            raise NotFound(f"task {task_id}")
        return self.project(str(task["project_id"]))


class Project:
    def __init__(self, kb: Kanboard, data: dict):
        self.kb, self.data, self.id = kb, data, int(data["id"])

    @cached_property
    def meta(self) -> dict:
        columns, swimlanes, users, tags = self.kb.batch(
            [
                ("getColumns", {"project_id": self.id}),
                ("getAllSwimlanes", {"project_id": self.id}),
                ("getProjectUsers", {"project_id": self.id}),
                ("getTagsByProject", {"project_id": self.id}),
            ]
        )
        return {
            "columns": columns,
            "swimlanes": swimlanes,
            "users": {int(k): v for k, v in (users or {}).items()},
            "tags": tags or [],
        }

    def summary(self) -> dict:
        return {
            "id": self.id,
            "identifier": self.data.get("identifier"),
            "name": self.data["name"],
            "active": bool(int(self.data.get("is_active") or 0)),
            "url": f"{self.kb.web}/board/{self.id}",
        }

    def _item(self, kind: str, items: list[dict], key: str, ref: str) -> dict:
        for item in items:
            if str(item["id"]) == ref or str(item[key]).lower() == ref.lower():
                return item
        names = ", ".join(str(i[key]) for i in items)
        raise NotFound(f"{kind} {ref!r} (known: {names})")

    def _find(self, kind: str, items: list[dict], key: str, ref: str) -> int:
        return int(self._item(kind, items, key, ref)["id"])

    def column(self, ref: str) -> int:
        return self._find("column", self.meta["columns"], "title", ref)

    def swimlane(self, ref: str) -> int:
        return self._find("swimlane", self.meta["swimlanes"], "name", ref)

    def user(self, ref: str) -> int:
        if ref.lower() == "none":
            return 0
        if ref.lower() == "me":
            return int(self.kb.me["id"])
        users = [{"id": k, "name": v} for k, v in self.meta["users"].items()]
        return self._find("user", users, "name", ref)

    def tags(self, refs: tuple[str, ...]) -> list[str]:
        """Only existing tags: the board's tags are configured in ops."""
        return [self._item("tag", self.meta["tags"], "name", r)["name"] for r in refs]

    def tasks(self, query: str, *, description: bool = False) -> list[dict]:
        rows = self.kb.call("searchTasks", project_id=self.id, query=query) or []
        tags = self.kb.batch([("getTaskTags", {"task_id": r["id"]}) for r in rows])
        return [self.task(r, t, description) for r, t in zip(rows, tags, strict=True)]

    def task(self, row: dict, tags, description: bool) -> dict:
        users = self.meta["users"]
        out = {
            "id": int(row["id"]),
            "title": row["title"],
            "project": self.data.get("identifier") or self.data["name"],
            "column": row.get("column_name"),
            "swimlane": row.get("swimlane_name"),
            "position": number(row.get("position")),
            "status": "open" if int(row.get("is_active") or 0) else "closed",
            "assignee": row.get("assignee_username"),
            "creator": users.get(int(row.get("creator_id") or 0)),
            "tags": sorted((tags or {}).values()),
            "priority": number(row.get("priority")),
            "color": row.get("color_id"),
            "reference": row.get("reference") or None,
            "due": timestamp(row.get("date_due")),
            "created": timestamp(row.get("date_creation")),
            "modified": timestamp(row.get("date_modification")),
            "moved": timestamp(row.get("date_moved")),
            "completed": timestamp(row.get("date_completed")),
            "comments": number(row.get("nb_comments")),
            "subtasks": number(row.get("nb_subtasks")),
            "url": f"{self.kb.web}/task/{row['id']}",
            "column_id": number(row.get("column_id")),
            "swimlane_id": number(row.get("swimlane_id")),
            "assignee_id": number(row.get("owner_id")) or None,
        }
        if description:
            out["description"] = row.get("description") or ""
        return out

    def get_task(self, task_id: int) -> dict:
        found = self.tasks(f"id:{task_id}", description=True)
        if not found:
            raise NotFound(f"task {task_id}")
        return found[0]


def emit(data) -> None:
    fmt = click.get_current_context().find_root().params["output"]
    if fmt == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    elif fmt == "jsonl":
        for item in data if isinstance(data, list) else [data]:
            click.echo(json.dumps(item, ensure_ascii=False))
    else:
        console = Console()
        if isinstance(data, dict):
            data = [{"field": k, "value": v} for k, v in data.items()]
        if not data or not isinstance(data, list) or not isinstance(data[0], dict):
            console.print_json(json.dumps(data))
            return
        table = Table(show_lines=False)
        keys = [k for k in TABLE if k in data[0]] or list(data[0])
        for key in keys:
            table.add_column(key, overflow="fold")
        for item in data:
            table.add_row(*(text_cell(item.get(k)) for k in keys))
        console.print(table)


def text_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list | dict):
        return (
            ", ".join(map(str, value)) if isinstance(value, list) else json.dumps(value)
        )
    return str(value)


def kb() -> Kanboard:
    return click.get_current_context().ensure_object(Kanboard)


project_arg = click.argument("project")
task_arg = click.argument("task_id", type=int)


@click.group(help=__doc__)
@click.option(
    "-o",
    "--output",
    type=click.Choice(["json", "jsonl", "table"]),
    default="json",
    envvar="KANBOARD_OUTPUT",
    show_default=True,
)
@click.option("--url", envvar="KANBOARD_URL", default=DEFAULT_URL, show_default=True)
@click.option(
    "--web", envvar="KANBOARD_WEB_URL", default=DEFAULT_WEB, show_default=True
)
@click.option("--user", envvar="KANBOARD_USER", default=DEFAULT_USER, show_default=True)
@click.pass_context
def main(ctx: click.Context, output: str, url: str, web: str, user: str) -> None:
    ctx.obj = Kanboard(url, user, web)


@main.command(help="The user the token acts as.")
def whoami() -> None:
    me = kb().me
    emit({k: me.get(k) for k in ("id", "username", "name", "email", "role")})


@main.command(help="Projects you are a member of.")
def projects() -> None:
    emit([Project(kb(), p).summary() for p in kb().call("getMyProjects")])


@main.command(help="Columns, swimlanes and open task counts of a board.")
@project_arg
def board(project: str) -> None:
    p = kb().project(project)
    open_tasks = p.tasks("status:open")

    def count(**filters):
        return sum(all(t[k] == v for k, v in filters.items()) for t in open_tasks)

    emit(
        {
            **p.summary(),
            "columns": [
                {
                    "id": int(c["id"]),
                    "title": c["title"],
                    "open": count(column=c["title"]),
                }
                for c in p.meta["columns"]
            ],
            "swimlanes": [
                {
                    "id": int(s["id"]),
                    "name": s["name"],
                    "open": {
                        c["title"]: count(swimlane=s["name"], column=c["title"])
                        for c in p.meta["columns"]
                    },
                }
                for s in p.meta["swimlanes"]
                if s.get("is_active") in (True, 1, "1")
            ],
        }
    )


@main.command(help="Columns of a board.")
@project_arg
def columns(project: str) -> None:
    emit(
        [
            {
                "id": int(c["id"]),
                "title": c["title"],
                "position": number(c["position"]),
                "task_limit": number(c.get("task_limit")),
            }
            for c in kb().project(project).meta["columns"]
        ]
    )


@main.command(help="Swimlanes of a board.")
@project_arg
def swimlanes(project: str) -> None:
    emit(
        [
            {
                "id": int(s["id"]),
                "name": s["name"],
                "position": number(s.get("position")),
                "active": s.get("is_active") in (True, 1, "1"),
            }
            for s in kb().project(project).meta["swimlanes"]
        ]
    )


@main.command(help="Members of a project.")
@project_arg
def members(project: str) -> None:
    p = kb().project(project)
    roles = kb().batch(
        [
            ("getProjectUserRole", {"project_id": p.id, "user_id": u})
            for u in p.meta["users"]
        ]
    )
    emit(
        [
            {"id": u, "name": n, "role": r}
            for (u, n), r in zip(p.meta["users"].items(), roles, strict=True)
        ]
    )


@main.command(help="Tags of a project.")
@project_arg
def tags(project: str) -> None:
    emit(
        [{"id": t["id"], "name": t["name"]} for t in kb().project(project).meta["tags"]]
    )


@main.command(
    help="Tasks of a project. QUERY uses Kanboard's search syntax, e.g. "
    "'assignee:me due:<2026-12-01'; the options add to it."
)
@project_arg
@click.argument("query", required=False, default="")
@click.option("--column")
@click.option("--swimlane")
@click.option("--assignee", help="Username, 'me' or 'nobody'.")
@click.option("--tag")
@click.option(
    "--status", type=click.Choice(list(STATUS)), default="open", show_default=True
)
@click.option("--full", is_flag=True, help="Include descriptions.")
def tasks(project, query, column, swimlane, assignee, tag, status, full) -> None:
    p = kb().project(project)
    # Kanboard answers an unknown name with no tasks; resolve names so typos fail.
    if column:
        column = p._item("column", p.meta["columns"], "title", column)["title"]
    if swimlane:
        swimlane = p._item("swimlane", p.meta["swimlanes"], "name", swimlane)["name"]
    if tag:
        tag = p.tags((tag,))[0]
    parts = [query] if query else []
    for key, value in (
        ("column", column),
        ("swimlane", swimlane),
        ("assignee", assignee),
        ("tag", tag),
    ):
        if value:
            parts.append(f'{key}:"{value}"')
    if "status:" not in query and STATUS[status]:
        parts.append(STATUS[status])
    emit(p.tasks(" ".join(parts), description=full))


@main.group(help="Show and change single tasks.")
def task() -> None:
    pass


@task.command("show", help="A task with its description.")
@task_arg
@click.option("--comments", is_flag=True)
@click.option("--subtasks", is_flag=True)
@click.option("--links", is_flag=True, help="Task links and external links.")
def task_show(task_id, comments, subtasks, links) -> None:
    p = kb().task_project(task_id)
    out = p.get_task(task_id)
    extra = [
        (flag, call)
        for flag, call in (
            ("comments", ("getAllComments", {"task_id": task_id})),
            ("subtasks", ("getAllSubtasks", {"task_id": task_id})),
            ("links", ("getAllTaskLinks", {"task_id": task_id})),
            ("external_links", ("getAllExternalTaskLinks", {"task_id": task_id})),
        )
        if {
            "comments": comments,
            "subtasks": subtasks,
            "links": links,
            "external_links": links,
        }[flag]
    ]
    for (flag, _), result in zip(extra, kb().batch([c for _, c in extra]), strict=True):
        out[flag] = SHAPES[flag](result or [])
    emit(out)


SHAPES = {
    "comments": lambda rows: [
        {
            "id": int(c["id"]),
            "author": c.get("username"),
            "created": timestamp(c.get("date_creation")),
            "text": c["comment"],
        }
        for c in rows
    ],
    "subtasks": lambda rows: [
        {
            "id": int(s["id"]),
            "title": s["title"],
            "status": SUBTASK_STATUS.get(int(s["status"])),
            "assignee": s.get("username"),
        }
        for s in rows
    ],
    "links": lambda rows: [
        {
            "id": int(link["id"]),
            "label": link.get("label"),
            "task_id": int(link["task_id"]),
            "title": link.get("title"),
        }
        for link in rows
    ],
    "external_links": lambda rows: [
        {"id": int(link["id"]), "title": link.get("title"), "url": link["url"]}
        for link in rows
    ],
}


def task_fields(f):
    for decorator in reversed(
        [
            click.option("--title"),
            click.option("--description", help="Text, '-' for stdin or @file."),
            click.option("--column"),
            click.option("--swimlane"),
            click.option("--assignee", help="Username, 'me' or 'none'."),
            click.option(
                "--tag",
                "tag",
                multiple=True,
                help="Repeat for several; replaces the tags.",
            ),
            click.option(
                "--reference", help="External reference, e.g. forgejo:billing#50."
            ),
            click.option("--due", help="YYYY-MM-DD"),
            click.option("--priority", type=int),
            click.option("--color", help="Kanboard color ID, e.g. red."),
        ]
    ):
        f = decorator(f)
    return f


def task_params(p: Project, o: dict) -> dict:
    params = {
        "title": o.get("title"),
        "description": text(o.get("description")),
        "reference": o.get("reference"),
        "date_due": o.get("due"),
        "priority": o.get("priority"),
        "color_id": o.get("color"),
    }
    if o.get("assignee"):
        params["owner_id"] = p.user(o["assignee"])
    if o.get("tag"):
        params["tags"] = p.tags(o["tag"])
    return {k: v for k, v in params.items() if v is not None}


def create(p: Project, o: dict) -> dict:
    if not o.get("title"):
        raise click.UsageError("--title is required")
    params = task_params(p, o) | {"project_id": p.id}
    if o.get("column"):
        params["column_id"] = p.column(o["column"])
    if o.get("swimlane"):
        params["swimlane_id"] = p.swimlane(o["swimlane"])
    return p.get_task(kb().change("createTask", **params))


@task.command("create", help="Create a task (first column and swimlane unless given).")
@project_arg
@task_fields
def task_create(project, **o) -> None:
    emit(create(kb().project(project), o))


@task.command(
    "ensure",
    help="Create a task unless one with --reference exists; prints it with created true/false.",
)
@project_arg
@task_fields
def task_ensure(project, **o) -> None:
    if not o.get("reference"):
        raise click.UsageError("--reference is required")
    p = kb().project(project)
    found = kb().call("getTaskByReference", project_id=p.id, reference=o["reference"])
    emit(
        {
            **(p.get_task(int(found["id"])) if found else create(p, o)),
            "created": not found,
        }
    )


@task.command("update", help="Change fields; --column/--swimlane move the task.")
@task_arg
@task_fields
def task_update(task_id, **o) -> None:
    p = kb().task_project(task_id)
    params = task_params(p, o)
    if params:
        kb().change("updateTask", id=task_id, **params)
    if o.get("column") or o.get("swimlane"):
        move(p, task_id, o.get("column"), o.get("swimlane"), 1)
    emit(p.get_task(task_id))


def move(p: Project, task_id: int, column, swimlane, position: int) -> None:
    current = p.get_task(task_id)
    kb().change(
        "moveTaskPosition",
        project_id=p.id,
        task_id=task_id,
        column_id=p.column(column) if column else current["column_id"],
        swimlane_id=p.swimlane(swimlane) if swimlane else current["swimlane_id"],
        position=position,
    )


@task.command("move", help="Move to a column and/or swimlane (top by default).")
@task_arg
@click.option("--column")
@click.option("--swimlane")
@click.option("--position", type=int, default=1, show_default=True)
def task_move(task_id, column, swimlane, position) -> None:
    if not column and not swimlane:
        raise click.UsageError("give --column and/or --swimlane")
    p = kb().task_project(task_id)
    move(p, task_id, column, swimlane, position)
    emit(p.get_task(task_id))


@task.command("assign", help="Assign to USER ('me', 'none' unassigns).")
@task_arg
@click.argument("user")
def task_assign(task_id, user) -> None:
    p = kb().task_project(task_id)
    kb().change("updateTask", id=task_id, owner_id=p.user(user))
    emit(p.get_task(task_id))


@task.command("close")
@task_arg
def task_close(task_id) -> None:
    p = kb().task_project(task_id)
    kb().change("closeTask", task_id=task_id)
    emit(p.get_task(task_id))


@task.command("reopen")
@task_arg
def task_reopen(task_id) -> None:
    p = kb().task_project(task_id)
    kb().change("openTask", task_id=task_id)
    emit(p.get_task(task_id))


@main.group(help="Task comments.")
def comment() -> None:
    pass


@comment.command("list")
@task_arg
def comment_list(task_id) -> None:
    emit(SHAPES["comments"](kb().call("getAllComments", task_id=task_id) or []))


@comment.command("add", help="TEXT is literal, '-' for stdin or @file.")
@task_arg
@click.argument("content")
def comment_add(task_id, content) -> None:
    comment_id = kb().change(
        "createComment",
        task_id=task_id,
        user_id=int(kb().me["id"]),
        content=text(content),
    )
    emit(SHAPES["comments"]([kb().call("getComment", comment_id=comment_id)])[0])


@main.group(help="Task subtasks.")
def subtask() -> None:
    pass


@subtask.command("add")
@task_arg
@click.argument("title")
@click.option("--assignee")
def subtask_add(task_id, title, assignee) -> None:
    params = {"task_id": task_id, "title": title}
    if assignee:
        params["user_id"] = kb().task_project(task_id).user(assignee)
    subtask_id = kb().change("createSubtask", **params)
    emit(SHAPES["subtasks"]([kb().call("getSubtask", subtask_id=subtask_id)])[0])


@subtask.command("done", help="Mark a subtask done (status todo/done with --status).")
@click.argument("subtask_id", type=int)
@click.option(
    "--status", type=click.Choice(["todo", "in progress", "done"]), default="done"
)
def subtask_done(subtask_id, status) -> None:
    current = kb().call("getSubtask", subtask_id=subtask_id)
    if not current:
        raise NotFound(f"subtask {subtask_id}")
    code = {v: k for k, v in SUBTASK_STATUS.items()}[status]
    kb().change(
        "updateSubtask", id=subtask_id, task_id=int(current["task_id"]), status=code
    )
    emit(SHAPES["subtasks"]([kb().call("getSubtask", subtask_id=subtask_id)])[0])


@main.group(help="External links of tasks.")
def link() -> None:
    pass


@link.command("add")
@task_arg
@click.argument("url")
@click.option("--title")
def link_add(task_id, url, title) -> None:
    params = {
        "task_id": task_id,
        "url": url,
        "dependency": "related",
        "type": "weblink",
    }
    kb().change(
        "createExternalTaskLink", **params | ({"title": title} if title else {})
    )
    emit(
        SHAPES["external_links"](
            kb().call("getAllExternalTaskLinks", task_id=task_id) or []
        )
    )


@main.command(help="Recent activity of a project.")
@project_arg
@click.option(
    "--since", default="7d", show_default=True, help="Age like 12h, 7d or 4w."
)
def activity(project, since) -> None:
    units = {"h": "hours", "d": "days", "w": "weeks"}
    if not (since[:-1].isdigit() and since[-1] in units):
        raise click.BadParameter("use e.g. 12h, 7d or 4w", param_hint="--since")
    cutoff = datetime.now(UTC) - timedelta(**{units[since[-1]]: int(since[:-1])})
    events = kb().call("getProjectActivity", project_id=kb().project(project).id) or []
    emit(
        [
            {
                "id": int(e["id"]),
                "date": timestamp(e["date_creation"]),
                "event": e["event_name"],
                "author": e.get("author_username"),
                "task_id": number(e.get("task_id")),
                "title": e.get("event_title"),
            }
            for e in events
            if int(e["date_creation"]) >= cutoff.timestamp()
        ]
    )


@main.command(
    help="Call any API procedure; PARAMS is a JSON object, '-' for stdin or @file."
)
@click.argument("method")
@click.argument("params", required=False, default="{}")
def call(method, params) -> None:
    try:
        parsed = json.loads(text(params) or "{}")
    except json.JSONDecodeError as error:
        raise click.BadParameter(str(error), param_hint="PARAMS") from None
    emit(kb().call(method, **parsed))
