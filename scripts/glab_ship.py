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
@click.option(
    "--squash/--no-squash",
    default=None,
    help="Squash commits on merge (default: project setting).",
)
@click.option(
    "-t",
    "--title",
    help="MR title, also applied to a reused MR (default: last commit subject).",
)
def main(squash: bool | None, title: str | None):
    """Push the current branch, reuse its open MR or open one titled after the
    last commit, auto-merge it with approvals temporarily disabled, switch back
    to the target branch, deleting the local branch if fully merged, then wait
    for the pipeline on the merged target branch.

    A merge commit as HEAD needs --title, e.g. a Conventional Commits title
    for MR title linting.
    """
    # turn kill/closed tab into SystemExit so approval rules get restored
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    try:
        ship(squash, title)
    except BaseException as e:
        osc("9;4;0" if isinstance(e, (KeyboardInterrupt, click.Abort)) else "9;4;2")
        raise
    osc("9;4;0")


def create_mr(branch: str, target: str, title: str, fields: list[str]) -> dict:
    """Open the MR, retrying while GitLab still processes the push of a new branch."""
    args = (
        "projects/:id/merge_requests",
        "-X",
        "POST",
        "-f",
        f"source_branch={branch}",
        "-f",
        f"target_branch={target}",
        "-f",
        f"title={title}",
        "-F",
        "remove_source_branch=true",
        *fields,
    )
    for _ in range(4):
        try:
            return api(*args)
        except subprocess.CalledProcessError:
            time.sleep(2)
    return api(*args)


def merge(
    branch: str, target: str, mr: dict | None, squash: bool | None, title: str | None
) -> dict:
    """Push, reuse or open the MR and merge it with approvals temporarily disabled."""
    if not mr and not title and len(git("log", "-1", "--format=%P").split()) > 1:
        raise click.ClickException("HEAD is a merge commit, pass --title")
    # set before the push or at creation, so the MR pipeline sees title and squash
    fields = [] if squash is None else ["-F", f"squash={str(squash).lower()}"]
    if mr and (title or fields):
        fields += ["-f", f"title={title}"] if title else []
        mr = api(f"projects/:id/merge_requests/{mr['iid']}", "-X", "PUT", *fields)
    show("pushing")
    subprocess.check_call(["git", "push", "-u", "origin", branch])
    rules = approval_rules(target)
    set_rules(dict.fromkeys(rules, 0))
    try:
        mr = mr or create_mr(
            branch, target, title or git("log", "-1", "--format=%s"), fields
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


def ship(squash: bool | None, title: str | None = None):
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
        mr = merge(branch, target, mr, squash, title)
    else:
        click.echo(f"MR !{mr['iid']} already merged: {mr['web_url']}")

    sha = mr["merge_commit_sha"] or mr["sha"]
    # git refuses checkout/pull if local changes would be overwritten
    if (
        subprocess.call(["git", "checkout", target]) == 0
        and subprocess.call(["git", "pull", "--ff-only"]) == 0
        and subprocess.call(
            ["git", "merge-base", "--is-ancestor", f"refs/heads/{branch}", "HEAD"]
        )
        == 0
    ):
        subprocess.call(["git", "branch", "-d", branch])

    wait_pipeline(sha, target)
    done = f"✓ !{mr['iid']} merged"
    for release in api("projects/:id/releases"):
        if release["commit"]["id"] == sha:
            click.echo(f"release {release['tag_name']}: {release['_links']['self']}")
            done = f"✓ released {release['tag_name']}"
    show(done, 1, 1)


if __name__ == "__main__":
    main()
