import json
import re
import signal
import sys
import time
from pathlib import Path

import questionary
import rich_click as click
import yaml
from rich.console import Group
from rich.live import Live
from rich.table import Table

from scripts.glab_ship import FINISHED, api, osc, show

ICONS = {
    "success": "[green]✔[/]",
    "failed": "[red]✘[/]",
    "canceled": "[red]⊘[/]",
    "skipped": "[dim]»[/]",
    "manual": "[yellow]⏵[/]",
    "running": "[blue]⟳[/]",
    "pending": "[yellow]…[/]",
    "created": "[dim]○[/]",
}


def gql(query: str, **variables):
    # glab sends an empty body for graphql --input; -F parses JSON, -f keeps strings
    args = ["-f", f"query={query}"]
    for k, v in variables.items():
        args += (
            ["-f", f"{k}={v}"] if isinstance(v, str) else ["-F", f"{k}={json.dumps(v)}"]
        )
    return api("graphql", *args)["data"]


def inputs() -> dict:
    """spec:inputs from the header document of .gitlab-ci.yml."""
    head = Path(".gitlab-ci.yml").read_text().split("\n---\n", 1)
    return len(head) > 1 and yaml.safe_load(head[0])["spec"]["inputs"] or {}


def create(project: str, ref: str, name: str, value) -> dict:
    """Create a pipeline with the given input (source=api, the CI rules must allow it)."""
    r = gql(
        """mutation($p: ID!, $r: String!, $i: [CiInputsInput!]) {
          pipelineCreate(input: {projectPath: $p, ref: $r, inputs: $i}) { errors pipeline { id } }
        }""",
        p=project,
        r=ref,
        i=[{"name": name, "value": value}],
    )["pipelineCreate"]
    if r["errors"]:
        raise click.ClickException("; ".join(r["errors"]))
    pipeline = api(f"projects/:id/pipelines/{r['pipeline']['id'].rsplit('/', 1)[1]}")
    names = [j["name"] for j in jobs(":id", pipeline["id"])]
    if missing := [
        e
        for e in (value if isinstance(value, list) else [value])
        if not any(re.match(rf"deploy_{e}(_|$)", n) for n in names)
    ]:
        raise click.ClickException(
            f"no deploy job for {', '.join(missing)} in {pipeline['web_url']}"
            ' (do the CI rules allow $CI_PIPELINE_SOURCE == "api"?)'
        )
    return pipeline


def jobs(project, pipeline_id: int) -> list[dict]:
    base = f"projects/{project}/pipelines/{pipeline_id}"
    return api(f"{base}/jobs?per_page=100") + api(f"{base}/bridges?per_page=100")


def choose(
    label: str, options: list[str], given: tuple[str, ...], default
) -> list[str]:
    if given:
        return list(given)
    picked = questionary.checkbox(
        label, [questionary.Choice(o, o, checked=o in default) for o in options]
    ).ask()
    if not picked:
        raise click.Abort()
    return picked


class Run:
    def __init__(self, label: str, pipeline: dict, targets: set[str] | None = None):
        self.label, self.pipeline, self.targets = label, pipeline, targets
        self.jobs: list[dict] = []

    def poll(self) -> bool:
        self.pipeline = api(f"projects/:id/pipelines/{self.pipeline['id']}")
        self.jobs = jobs(":id", self.pipeline["id"])
        for j in self.jobs:
            if ds := j.get("downstream_pipeline"):
                j["downstream"] = api(
                    f"projects/{ds['project_id']}/pipelines/{ds['id']}"
                )
                j["downstream"]["jobs"] = jobs(ds["project_id"], ds["id"])
        mine = [
            j for j in self.jobs if self.targets is None or j["name"] in self.targets
        ]
        return self.pipeline["status"] in FINISHED or (
            self.pipeline["status"] == "manual"
            and all(j["status"] in FINISHED for j in mine)
        )

    def ok(self) -> bool:
        if self.targets is None:
            return self.pipeline["status"] == "success"
        return all(
            j["status"] == "success" for j in self.jobs if j["name"] in self.targets
        )

    def progress(self) -> tuple[int, int]:
        """Finished (or waiting manual) jobs including downstream pipelines."""
        all_jobs = self.jobs + [
            d for j in self.jobs for d in j.get("downstream", {}).get("jobs", [])
        ]
        return sum(j["status"] in (*FINISHED, "manual") for j in all_jobs), len(
            all_jobs
        )

    def render(self) -> Table:
        p = self.pipeline
        t = Table(
            title=f"{ICONS.get(p['status'], '?')} [bold]{self.label}[/] {p['status']} [link={p['web_url']}]#{p['id']}[/]",
            title_justify="left",
            show_header=False,
            box=None,
            padding=(0, 1),
        )
        for j in sorted(self.jobs, key=lambda j: j["id"]):
            row = [
                f"  {ICONS.get(j['status'], '?')}",
                j["stage"],
                j["name"],
                j["status"],
            ]
            if ds := j.get("downstream"):
                done = sum(d["status"] in FINISHED for d in ds["jobs"])
                name = ds["web_url"].split("/-/")[0].rsplit("/", 1)[1]
                row[3] += (
                    f" → [link={ds['web_url']}]{name} #{ds['id']}[/]"
                    f" {ds['status']} ({done}/{len(ds['jobs'])})"
                )
            t.add_row(*row)
        return t


def watch(runs: list[Run]):
    with Live(auto_refresh=False) as live:
        while True:
            done = [r.poll() for r in runs]
            live.update(Group(*(r.render() for r in runs)), refresh=True)
            done_jobs, total = map(sum, zip(*(r.progress() for r in runs)))
            labels = ",".join(r.label for r in runs)
            show(f"{labels} {done_jobs}/{total}", done_jobs, total)
            if all(done):
                break
            time.sleep(5)
    failed = [r.label for r in runs if not r.ok()]
    if failed:
        raise click.ClickException(f"failed: {', '.join(failed)}")
    show(f"✓ deployed {', '.join(r.label for r in runs)}", 1, 1)


@click.command()
@click.option(
    "-e",
    "--env",
    "envs",
    multiple=True,
    help="Environment (repeatable); prompts if omitted.",
)
@click.option("-r", "--ref", help="Ref to deploy, defaults to the default branch.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation.")
def main(envs: tuple[str, ...], ref: str | None, yes: bool):
    """Deploy the current GitLab project and watch the pipelines.

    Reads the spec:inputs header of .gitlab-ci.yml: a single-choice input
    starts one web pipeline per selected environment in parallel, an array
    input starts one pipeline with all selected environments. Without inputs,
    the manual jobs of the latest pipeline on the ref are played instead.
    Downstream deploy pipelines are watched as well.
    """
    # turn kill/closed tab into SystemExit so the progress bar shows the error
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    try:
        deploy(envs, ref, yes)
    except BaseException as e:
        osc("9;4;0" if isinstance(e, click.Abort) else "9;4;2")
        raise
    osc("9;4;0")


def deploy(envs: tuple[str, ...], ref: str | None, yes: bool):
    project = api("projects/:id")
    ref = ref or project["default_branch"]
    commit = api(f"projects/:id/repository/commits/{ref}")
    click.echo(
        f"{project['path_with_namespace']} @ {ref} {commit['short_id']} {commit['title']}"
    )

    name, spec = next(
        ((n, s) for n, s in inputs().items() if s.get("options")), ("", None)
    )
    if spec:
        array = spec.get("type") == "array"
        default = spec.get("default", [])
        picked = choose(
            f"{name}:", spec["options"], envs, default if array else [default]
        )
        plan = [(",".join(picked), picked)] if array else [(e, e) for e in picked]
        if (
            not yes
            and not questionary.confirm(
                f"start {len(plan)} pipeline(s): {', '.join(p[0] for p in plan)}?"
            ).ask()
        ):
            raise click.Abort()
        show(f"starting {len(plan)} pipeline(s)")
        runs = [
            Run(label, create(project["path_with_namespace"], ref, name, v))
            for label, v in plan
        ]
    else:
        pipeline = api(f"projects/:id/pipelines?ref={ref}&per_page=1")[0]
        manual = {
            j["name"]: j for j in jobs(":id", pipeline["id"]) if j["status"] == "manual"
        }
        if not manual:
            raise click.ClickException(f"no manual jobs in {pipeline['web_url']}")
        picked = choose("jobs:", sorted(manual), envs, [])
        if (
            not yes
            and not questionary.confirm(
                f"play {', '.join(picked)} in {pipeline['web_url']}?"
            ).ask()
        ):
            raise click.Abort()
        show(f"playing {', '.join(picked)}")
        for j in picked:
            api(f"projects/:id/jobs/{manual[j]['id']}/play", "-X", "POST")
        runs = [Run(ref, pipeline, set(picked))]
    watch(runs)


if __name__ == "__main__":
    main()
