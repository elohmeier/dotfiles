import json
import subprocess
import time

import rich_click as click


def api(path: str, *args: str):
    return json.loads(subprocess.check_output(["glab", "api", *args, path]))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def poll(fn, interval: int = 10):
    while (result := fn()) is None:
        time.sleep(interval)
    return result


def approval_rules(target: str) -> dict[int, int]:
    """Approval rules requiring approvals that apply to the target branch."""
    protected = {b["name"] for b in api("projects/:id/protected_branches")}

    def applies(rule) -> bool:
        if rule["applies_to_all_protected_branches"]:
            return target in protected
        names = [b["name"] for b in rule["protected_branches"]]
        return not names or target in names

    return {
        r["id"]: r["approvals_required"]
        for r in api("projects/:id/approval_rules")
        if r["approvals_required"] > 0 and applies(r)
    }


def set_rules(rules: dict[int, int]):
    for rule_id, n in rules.items():
        api(
            f"projects/:id/approval_rules/{rule_id}",
            "-X",
            "PUT",
            "-F",
            f"approvals_required={n}",
        )
        click.echo(f"approval rule {rule_id}: approvals_required={n}")


def wait_pipeline(sha: str, ref: str):
    pipeline = poll(
        lambda: next(iter(api(f"projects/:id/pipelines?sha={sha}&ref={ref}")), None), 5
    )
    click.echo(f"{ref} pipeline: {pipeline['web_url']}")
    status = poll(
        lambda: (
            s
            if (s := api(f"projects/:id/pipelines/{pipeline['id']}")["status"])
            in ("success", "failed", "canceled", "skipped")
            else None
        )
    )
    if status != "success":
        raise click.ClickException(f"{ref} pipeline {status}")
    click.echo(f"{ref} pipeline: success")


@click.command()
def main():
    """Push the current branch, reuse its open MR or open one titled after the
    last commit, auto-merge it with approvals temporarily disabled, then wait
    for the pipeline on the merged target branch.
    """
    branch = git("branch", "--show-current")
    target = api("projects/:id")["default_branch"]
    subprocess.check_call(["git", "push", "-u", "origin", branch])

    rules = approval_rules(target)
    set_rules(dict.fromkeys(rules, 0))
    try:
        mr = next(
            iter(
                api(f"projects/:id/merge_requests?source_branch={branch}&state=opened")
            ),
            None,
        ) or api(
            "projects/:id/merge_requests",
            "-X",
            "POST",
            "-f",
            f"source_branch={branch}",
            "-f",
            f"target_branch={target}",
            "-f",
            f"title={git('log', '-1', '--format=%s')}",
            "-F",
            "remove_source_branch=true",
        )
        click.echo(mr["web_url"])
        mr_path = f"projects/:id/merge_requests/{mr['iid']}"
        poll(lambda: api(mr_path)["head_pipeline"], 5)
        subprocess.check_call(
            ["glab", "mr", "merge", str(mr["iid"]), "--auto-merge", "--yes"]
        )

        def merged():
            mr = api(mr_path)
            if mr["state"] == "closed":
                raise click.ClickException("MR closed")
            if (s := mr["head_pipeline"]["status"]) in ("failed", "canceled"):
                raise click.ClickException(f"MR pipeline {s}")
            if mr["detailed_merge_status"] == "mergeable" and s == "success":
                # auto-merge does not re-evaluate after approval rules change
                subprocess.check_call(["glab", "mr", "merge", str(mr["iid"]), "--yes"])
            return mr if mr["state"] == "merged" else None

        mr = poll(merged)
        click.echo(f"MR !{mr['iid']} merged")
    finally:
        set_rules(rules)

    sha = mr["merge_commit_sha"] or mr["sha"]
    wait_pipeline(sha, target)
    for release in api("projects/:id/releases"):
        if release["commit"]["id"] == sha:
            click.echo(f"release {release['tag_name']}: {release['_links']['self']}")

    # git refuses checkout/pull if local changes would be overwritten
    if subprocess.call(["git", "checkout", target]) == 0:
        subprocess.call(["git", "pull", "--ff-only"])


if __name__ == "__main__":
    main()
