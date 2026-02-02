"""Explore Prometheus/Thanos metrics with samples."""

from __future__ import annotations

import concurrent.futures
import json
import re
import time

import requests
import rich_click as click
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

console = Console(stderr=True)


def _get_json(session, url, path, params=None, log=None, timeout=None):
    full_url = f"{url.rstrip('/')}{path}"
    started = time.monotonic()
    if log:
        log(f"GET {full_url} params={params or {}}")
    resp = session.get(full_url, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "success":
        raise click.ClickException(str(payload))
    data = payload.get("data")
    if log:
        elapsed = time.monotonic() - started
        size = len(data) if isinstance(data, list) else "?"
        log(f"OK  {full_url} {elapsed:.2f}s items={size}")
    return data


def _metric_names(session, url, log=None, timeout=None):
    return _get_json(
        session, url, "/api/v1/label/__name__/values", log=log, timeout=timeout
    )


def _instant_query(session, url, query, selector, log=None, timeout=None):
    selector = selector.strip() if selector else ""
    if selector.startswith("{") and selector.endswith("}"):
        selector = selector[1:-1].strip()
    label_part = f",{selector}" if selector else ""
    promql = f'{{__name__="{query}"{label_part}}}'
    started = time.monotonic()
    data = _get_json(
        session,
        url,
        "/api/v1/query",
        params={"query": promql},
        log=log,
        timeout=timeout,
    )
    return data.get("result", []), time.monotonic() - started


def _format_labels(labels):
    return json.dumps(labels, ensure_ascii=True, sort_keys=True)


def _emit_table(rows, include_sample, include_stats, include_latency):
    table = Table(title="Metrics")
    table.add_column("Metric")
    if include_stats:
        table.add_column("Series")
    if include_sample:
        table.add_column("Sample Labels")
        table.add_column("Sample Value")
        table.add_column("Sample TS")
    if include_latency:
        table.add_column("Query s")
    for row in rows:
        cells = [row["metric"]]
        if include_stats:
            cells.append(str(row.get("series", 0)))
        if include_sample:
            sample = row.get("sample")
            if sample:
                cells.extend(
                    [
                        _format_labels(sample["labels"]),
                        str(sample["value"]),
                        str(sample["ts"]),
                    ]
                )
            else:
                cells.extend(["", "", ""])
        if include_latency:
            latency = row.get("query_s")
            cells.append(f"{latency:.2f}" if latency is not None else "")
        table.add_row(*cells)
    console.print(table)


def _emit_jsonl(rows):
    for row in rows:
        print(json.dumps(row, ensure_ascii=True, sort_keys=True))


def _filter_names(names, regex, match):
    if regex:
        pattern = re.compile(regex)
        names = [name for name in names if pattern.search(name)]
    if match:
        needle = match.lower()
        names = [name for name in names if needle in name.lower()]
    return names


@click.group(invoke_without_command=True)
@click.option(
    "--url",
    envvar="PROM_URL",
    default="http://localhost:9090",
    show_default=True,
    help="Prometheus/Thanos base URL.",
)
@click.option("--verbose", is_flag=True, help="Log request timing to stderr.")
@click.option("--timeout", type=float, help="Request timeout in seconds.")
@click.option("--regex", help="Regex filter for metric names.")
@click.option("--match", help="Substring match for metric names.")
@click.option("--limit", type=int, help="Limit number of metrics.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "jsonl"]),
    default="table",
    show_default=True,
)
@click.pass_context
def main(ctx, url, verbose, timeout, regex, match, limit, fmt):
    """Explore available metrics, then sample them."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["verbose"] = verbose
    ctx.obj["regex"] = regex
    ctx.obj["match"] = match
    ctx.obj["limit"] = limit
    ctx.obj["format"] = fmt
    ctx.obj["timeout"] = timeout
    if ctx.invoked_subcommand is None:
        ctx.invoke(list_metrics)


@main.command("list")
@click.pass_context
def list_metrics(ctx):
    """List metric names."""
    session = requests.Session()
    log = console.log if ctx.obj["verbose"] else None
    if log:
        log(f"Base URL: {ctx.obj['url']}")
    names = list(
        _metric_names(session, ctx.obj["url"], log=log, timeout=ctx.obj["timeout"])
    )
    names = _filter_names(names, ctx.obj["regex"], ctx.obj["match"])
    names.sort()
    if ctx.obj["limit"]:
        names = names[: ctx.obj["limit"]]
    rows = [{"metric": name} for name in names]
    if ctx.obj["format"] == "table":
        _emit_table(
            rows, include_sample=False, include_stats=False, include_latency=False
        )
    else:
        _emit_jsonl(rows)


@main.command("sample")
@click.option("--sample/--no-sample", default=True, help="Include one sample.")
@click.option("--stats/--no-stats", default=False, help="Include series count.")
@click.option(
    "--selector",
    help='Label selector to apply (e.g. cluster="prod",namespace=~"kube-.*").',
)
@click.option(
    "--show-latency",
    is_flag=True,
    help="Show per-query latency in the output table.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel workers for queries.",
)
@click.pass_context
def sample_metrics(ctx, sample, stats, selector, show_latency, workers):
    """Sample metrics with optional stats."""
    session = requests.Session()
    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(show_speed=True),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )
    log = progress.console.log if ctx.obj["verbose"] else None
    if log:
        log(f"Base URL: {ctx.obj['url']}")
    names = list(
        _metric_names(session, ctx.obj["url"], log=log, timeout=ctx.obj["timeout"])
    )
    names = _filter_names(names, ctx.obj["regex"], ctx.obj["match"])
    names.sort()
    if ctx.obj["limit"]:
        names = names[: ctx.obj["limit"]]

    def _fetch_row(idx, name):
        if log:
            log(f"Metric {idx}/{total}: {name}")
        row = {"metric": name}
        if sample or stats:
            local_session = requests.Session()
            result, elapsed = _instant_query(
                local_session,
                ctx.obj["url"],
                name,
                selector,
                log=log,
                timeout=ctx.obj["timeout"],
            )
            if stats:
                row["series"] = len(result)
            if sample and result:
                sample_row = result[0]
                row["sample"] = {
                    "labels": sample_row.get("metric", {}),
                    "value": sample_row.get("value", [None, None])[1],
                    "ts": sample_row.get("value", [None, None])[0],
                }
            if show_latency:
                row["query_s"] = elapsed
        return idx, row

    rows = [None] * len(names)
    total = len(names)
    with progress:
        task = progress.add_task("Querying metrics", total=total)
        if workers <= 1 or total == 0:
            for idx, name in enumerate(names, start=1):
                _, row = _fetch_row(idx, name)
                rows[idx - 1] = row
                progress.update(task, advance=1)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(_fetch_row, idx, name)
                    for idx, name in enumerate(names, start=1)
                ]
                for future in concurrent.futures.as_completed(futures):
                    idx, row = future.result()
                    rows[idx - 1] = row
                    progress.update(task, advance=1)

    if ctx.obj["format"] == "table":
        _emit_table(rows, sample, stats, show_latency)
    else:
        _emit_jsonl(rows)


if __name__ == "__main__":
    main()
