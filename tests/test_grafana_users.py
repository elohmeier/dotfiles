import httpx
from click.testing import CliRunner

from scripts.grafana import users


def test_partial_deletion_reports_success_count_and_fails(monkeypatch):
    def respond(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "totalCount": 2,
                    "users": [
                        {"id": n, "login": str(n), "lastSeenAt": "2020-01-01T00:00:00Z"}
                        for n in (1, 2)
                    ],
                },
            )
        return httpx.Response(200 if request.url.path.endswith("/1") else 403)

    monkeypatch.setattr(
        users,
        "client",
        lambda *args: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    result = CliRunner().invoke(
        users.cli,
        [
            "--url",
            "https://grafana.invalid",
            "--password",
            "test",
            "delete",
            "--min-days",
            "30",
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "Deleted 1 of 2 selected" in result.output


def test_user_administration_requires_admin_password():
    result = CliRunner().invoke(
        users.cli,
        ["--url", "https://grafana.invalid", "list"],
        env={"GRAFANA_PASSWORD": None},
    )
    assert result.exit_code == 2
    assert "--password" in result.output
