import json

import httpx
import pytest
from click.testing import CliRunner

from scripts import kanboard

PROJECT = {"id": 1, "identifier": "CONVEXIO", "name": "Convexio", "is_active": 1}
ROW = {
    "id": 118,
    "title": "Legal review",
    "description": "text",
    "column_name": "Backlog",
    "swimlane_name": "Product",
    "column_id": 1,
    "swimlane_id": 1,
    "position": "3",
    "is_active": "1",
    "assignee_username": None,
    "owner_id": 0,
    "creator_id": "2",
    "priority": 0,
    "reference": "",
    "date_due": 0,
    "date_creation": "1792822947",
    "nb_comments": 0,
    "nb_subtasks": 0,
}
API = {
    "getProjectByIdentifier": lambda p: (
        PROJECT if p["identifier"] == "CONVEXIO" else None
    ),
    "getProjectByName": lambda p: None,
    "getProjectById": lambda p: PROJECT,
    "getColumns": lambda p: [{"id": 1, "title": "Backlog", "position": 1}],
    "getAllSwimlanes": lambda p: [{"id": 1, "name": "Product", "is_active": True}],
    "getProjectUsers": lambda p: {"2": "enno"},
    "getTagsByProject": lambda p: [{"id": 1, "name": "bug"}],
    "searchTasks": lambda p: [ROW],
    "getTaskTags": lambda p: {"1": "bug"},
    "getTask": lambda p: {"id": p["task_id"], "project_id": 1},
    "getTaskByReference": lambda p: None,
    "createTask": lambda p: 118,
}


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Basic ")
        out = []
        for c in json.loads(request.content):
            seen.append((c["method"], c["params"]))
            if c["method"] not in API:
                out.append(
                    {
                        "jsonrpc": "2.0",
                        "id": c["id"],
                        "error": {"message": "Method not found"},
                    }
                )
            else:
                out.append(
                    {
                        "jsonrpc": "2.0",
                        "id": c["id"],
                        "result": API[c["method"]](c["params"]),
                    }
                )
        return httpx.Response(200, json=out)

    client = httpx.Client
    monkeypatch.setattr(
        kanboard.httpx,
        "Client",
        lambda **kw: client(**kw, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setenv("KANBOARD_TOKEN", "test-token")
    return seen


def run(*args):
    result = CliRunner().invoke(kanboard.main, args)
    return result, json.loads(result.output) if result.exit_code == 0 else None


def test_tasks_query_and_normalized_output(calls):
    result, tasks = run("tasks", "convexio", "--column", "backlog", "--tag", "BUG")
    assert result.exit_code == 0, result.output
    assert (
        "searchTasks",
        {"project_id": 1, "query": 'column:"Backlog" tag:"bug" status:open'},
    ) in calls
    task = tasks[0]
    assert task["id"] == 118 and task["position"] == 3 and task["status"] == "open"
    assert task["tags"] == ["bug"] and task["creator"] == "enno"
    assert task["created"].startswith("2026-10-2") and task["due"] is None
    assert task["url"] == "https://violet-ridge-anchor.hf40.de/task/118"
    assert "description" not in task


def test_unknown_names_fail_before_searching(calls):
    result, _ = run("tasks", "CONVEXIO", "--column", "Nope")
    assert result.exit_code == 3
    assert json.loads(result.stderr)["error"].startswith(
        "column 'Nope' (known: Backlog"
    )
    assert not any(m == "searchTasks" for m, _ in calls)


def test_ensure_creates_once_with_resolved_ids(calls, monkeypatch):
    result, task = run(
        "task",
        "ensure",
        "CONVEXIO",
        "--reference",
        "forgejo:billing#50",
        "--title",
        "Legal review",
        "--swimlane",
        "product",
        "--assignee",
        "enno",
        "--tag",
        "bug",
        "--description",
        "body",
    )
    assert result.exit_code == 0, result.output
    assert task["created"] is True and task["description"] == "text"
    create = next(p for m, p in calls if m == "createTask")
    assert create == {
        "title": "Legal review",
        "description": "body",
        "reference": "forgejo:billing#50",
        "owner_id": 2,
        "tags": ["bug"],
        "project_id": 1,
        "swimlane_id": 1,
    }
    monkeypatch.setitem(API, "getTaskByReference", lambda p: {"id": 118})
    calls.clear()
    result, task = run(
        "task",
        "ensure",
        "CONVEXIO",
        "--reference",
        "forgejo:billing#50",
        "--title",
        "x",
    )
    assert task["created"] is False and not any(m == "createTask" for m, _ in calls)


def test_unknown_tags_are_not_created(calls):
    result, _ = run("task", "create", "CONVEXIO", "--title", "x", "--tag", "new")
    assert result.exit_code == 3 and not any(m == "createTask" for m, _ in calls)


def test_api_errors_are_json_with_exit_4(calls):
    result, _ = run("call", "nope")
    assert result.exit_code == 4
    assert json.loads(result.stderr) == {"error": "nope: Method not found"}


def test_refused_mutation_is_an_error(calls, monkeypatch):
    monkeypatch.setitem(API, "createTask", lambda p: False)
    result, _ = run("task", "create", "CONVEXIO", "--title", "x")
    assert result.exit_code == 4 and "createTask was refused" in result.stderr


def test_token_sources_in_order(monkeypatch):
    monkeypatch.delenv("KANBOARD_TOKEN", raising=False)
    monkeypatch.delenv("KANBOARD_TOKEN_COMMAND", raising=False)
    monkeypatch.setattr(kanboard, "host_secret", lambda name: f"host-{name}")
    assert kanboard.token() == "host-KANBOARD_TOKEN"
    monkeypatch.setenv("KANBOARD_TOKEN_COMMAND", "echo from-command")
    assert kanboard.token() == "from-command"
    monkeypatch.setenv("KANBOARD_TOKEN", "from-env")
    assert kanboard.token() == "from-env"
    monkeypatch.delenv("KANBOARD_TOKEN")
    monkeypatch.delenv("KANBOARD_TOKEN_COMMAND")
    monkeypatch.setattr(kanboard, "host_secret", lambda name: None)
    monkeypatch.setattr(kanboard, "host_storage", lambda: "macOS Keychain")
    with pytest.raises(kanboard.Error, match="secret-entry request --host"):
        kanboard.token()


def test_missing_token_without_host_storage(monkeypatch):
    monkeypatch.delenv("KANBOARD_TOKEN", raising=False)
    monkeypatch.delenv("KANBOARD_TOKEN_COMMAND", raising=False)
    monkeypatch.setattr(kanboard, "host_secret", lambda name: None)

    def unavailable():
        raise kanboard.SecretError("TPM unavailable")

    monkeypatch.setattr(kanboard, "host_storage", unavailable)
    result, _ = run("whoami")
    assert result.exit_code == 1
    error = json.loads(result.stderr)["error"]
    assert "KANBOARD_TOKEN_COMMAND" in error
    assert "pass show kanboard/token" in error
    assert "secret-entry request" not in error


def test_host_storage_errors_are_json(monkeypatch):
    monkeypatch.delenv("KANBOARD_TOKEN", raising=False)
    monkeypatch.delenv("KANBOARD_TOKEN_COMMAND", raising=False)

    def denied(name):
        raise kanboard.SecretError("Keychain access denied")

    monkeypatch.setattr(kanboard, "host_secret", denied)
    result, _ = run("whoami")
    assert result.exit_code == 1
    assert json.loads(result.stderr) == {"error": "Keychain access denied"}
