from io import StringIO
from urllib.parse import parse_qs, urlsplit

import pytest
from rich.console import Console

from scripts import glab_deploy


@pytest.mark.parametrize("targets", [None, {"deploy_itobs_in_deploy"}])
def test_approval_wait_continues_through_merge_and_rollout(monkeypatch, targets):
    source = {
        "id": 1091857,
        "status": "running",
        "web_url": "https://gitlab.example/source/-/pipelines/1091857",
    }
    downstream = {
        "id": 1091860,
        "project_id": 2039,
        "ref": "044e0095/itobs/608",
        "status": "running",
        "web_url": "https://gitlab.example/deploy/-/pipelines/1091860",
    }
    bridge = {
        "id": 3341820,
        "stage": "deploy",
        "name": "deploy_itobs_in_deploy",
        "status": "running",
        "downstream_pipeline": downstream,
    }
    gate = {"id": 3341843, "name": "wait_for_merge_request", "status": "created"}
    mr = {
        "iid": 467,
        "state": "opened",
        "description": "<!-- @@@1091860@@@608@@@044e0095/itobs/608@@@remotemonitoring -->",
        "web_url": "https://gitlab.example/deploy/-/merge_requests/467",
    }
    # Redeploys can reuse the same branch; only this pipeline's MR belongs here.
    old = {**mr, "description": "<!-- @@@1091800@@@608@@@old -->"}
    unrelated = {**mr, "description": None}
    mrs = [old, unrelated]

    def api(path):
        if path == "projects/:id/pipelines/1091857":
            return dict(source)
        if path == "projects/2039/pipelines/1091860":
            return dict(downstream)
        url = urlsplit(path)
        assert url.path == "projects/2039/merge_requests"
        assert parse_qs(url.query) == {
            "scope": ["all"],
            "source_branch": ["itobs-608-staging"],
            "target_branch": ["itobs-approved"],
        }
        return mrs

    monkeypatch.setattr(glab_deploy, "api", api)
    monkeypatch.setattr(
        glab_deploy,
        "jobs",
        lambda project, pipeline: (
            [dict(bridge)]
            if project == ":id"
            else [
                {
                    "name": "create_merge_request",
                    "status": "failed",
                    "allow_failure": True,
                },
                gate,
            ]
        ),
    )
    run = glab_deploy.Run("itobs,obsp", source, targets)

    for state, gate_status, deploy_status, parent_status in [
        (None, "created", "running", "running"),
        ("opened", "manual", "manual", "manual"),
        ("merged", "manual", "manual", "manual"),
        ("merged", "running", "running", "running"),
        ("merged", "success", "success", "running"),
        ("merged", "success", "success", "success"),
    ]:
        if state:
            mr["state"] = state
            mrs = [old, unrelated, mr]
        gate["status"] = gate_status
        downstream["status"] = deploy_status
        bridge["status"] = "success" if deploy_status == "success" else "running"
        source["status"] = parent_status

        assert run.poll() == (parent_status == "success")
        output = StringIO()
        Console(file=output, width=160).print(run.render())
        rendered = output.getvalue()
        if state:
            assert mr["web_url"] in rendered
            assert (
                "Waiting for deployment approval / merge"
                if state == "opened"
                else "Deployment approval MR merged"
            ) in rendered
        else:
            assert "merge_requests" not in rendered

    assert run.ok()


@pytest.mark.parametrize(
    "ref, jobs",
    [
        ("main", [{"name": "wait_for_merge_request"}]),
        ("release/itobs/latest", [{"name": "wait_for_merge_request"}]),
        ("044e0095/itobs/608", [{"name": "deploy"}]),
    ],
)
def test_other_pipelines_do_not_query_approval_mrs(monkeypatch, ref, jobs):
    def api(path):
        pytest.fail(f"unexpected API request: {path}")

    monkeypatch.setattr(glab_deploy, "api", api)
    assert glab_deploy.approval({"ref": ref, "jobs": jobs}) is None
