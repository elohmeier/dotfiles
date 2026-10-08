import json
import os
import signal
import subprocess
import sys
import time

import rich_click as click


def api(path: str, *args: str):
    return json.loads(subprocess.check_output(["glab", "api", *args, path]))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def osc(seq: str):
    if sys.stdout.isatty():
        sys.stdout.write(f"\033]{seq}\a")
        sys.stdout.flush()


def show(step: str, done: int | None = None, total: int = 0):
    """Set the tab title and Ghostty progress bar (OSC 9;4, indeterminate without done)."""
    osc(f"2;{os.path.basename(os.getcwd())}: {step}")
    osc("9;4;3" if done is None else f"9;4;1;{done * 100 // max(total, 1)}")


def show_pipeline(step: str, pipeline_id: int):
    jobs = api(f"projects/:id/pipelines/{pipeline_id}/jobs?per_page=100")
    done = sum(j["status"] in (*FINISHED, "manual") for j in jobs)
    show(f"{step} {done}/{len(jobs)}", done, len(jobs))


FINISHED = ("success", "failed", "canceled", "skipped")


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
    show(f"waiting for {ref} pipeline")
    pipeline = poll(
        lambda: next(iter(api(f"projects/:id/pipelines?sha={sha}&ref={ref}")), None), 5
    )
    click.echo(f"{ref} pipeline: {pipeline['web_url']}")

    def finished():
        show_pipeline(f"{ref} pipeline", pipeline["id"])
        s = api(f"projects/:id/pipelines/{pipeline['id']}")["status"]
        return s if s in FINISHED else None

    status = poll(finished)
    if status != "success":
        raise click.ClickException(f"{ref} pipeline {status}")
    click.echo(f"{ref} pipeline: success")


@click.command()
def main():
    """Push the current branch, reuse its open MR or open one titled after the
    last commit, auto-merge it with approvals temporarily disabled, then wait
    for the pipeline on the merged target branch.
    """
    # turn kill/closed tab into SystemExit so approval rules get restored
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    try:
        ship()
    except BaseException:
        osc("9;4;2")
        raise
    osc("9;4;0")


def merge(branch: str, target: str, mr: dict | None) -> dict:
    """Push, reuse or open the MR and merge it with approvals temporarily disabled."""
    show("pushing")
    subprocess.check_call(["git", "push", "-u", "origin", branch])
    rules = approval_rules(target)
    set_rules(dict.fromkeys(rules, 0))
    try:
        mr = mr or api(
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

        def merged():
            mr = api(mr_path)
            if mr["state"] == "merged":
                return mr
            if mr["state"] == "closed":
                raise click.ClickException("MR closed")
            if not mr["head_pipeline"]:
                show(f"!{mr['iid']} waiting for pipeline")
                return None
            show_pipeline(f"!{mr['iid']} pipeline", mr["head_pipeline"]["id"])
            if (s := mr["head_pipeline"]["status"]) in ("failed", "canceled"):
                raise click.ClickException(f"MR pipeline {s}")
            status = mr["detailed_merge_status"]
            # merging while GitLab rechecks mergeability/approvals returns 405;
            # an existing auto-merge is not re-evaluated after approval changes
            if status not in (
                "unchecked",
                "checking",
                "preparing",
                "approvals_syncing",
            ) and (not mr["merge_when_pipeline_succeeds"] or status == "mergeable"):
                subprocess.call(["glab", "mr", "merge", str(mr["iid"]), "--yes"])
            return None

        mr = poll(merged)
        click.echo(f"MR !{mr['iid']} merged")
        return mr
    finally:
        set_rules(rules)


def ship():
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    target = api("projects/:id")["default_branch"]
    if branch == target:
        raise click.ClickException(f"already on {target}")
    # resume: open MR for the branch, or an already merged one of the current HEAD
    mr = next(
        (
            m
            for m in api(f"projects/:id/merge_requests?source_branch={branch}")
            if m["state"] == "opened" or (m["state"] == "merged" and m["sha"] == head)
        ),
        None,
    )
    if not mr or mr["state"] == "opened":
        mr = merge(branch, target, mr)
    else:
        click.echo(f"MR !{mr['iid']} already merged: {mr['web_url']}")

    sha = mr["merge_commit_sha"] or mr["sha"]
    wait_pipeline(sha, target)
    done = f"✓ !{mr['iid']} merged"
    for release in api("projects/:id/releases"):
        if release["commit"]["id"] == sha:
            click.echo(f"release {release['tag_name']}: {release['_links']['self']}")
            done = f"✓ released {release['tag_name']}"
    show(done, 1, 1)

    # git refuses checkout/pull if local changes would be overwritten
    if subprocess.call(["git", "checkout", target]) == 0:
        subprocess.call(["git", "pull", "--ff-only"])


if __name__ == "__main__":
    main()
