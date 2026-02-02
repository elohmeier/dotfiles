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


def _metadata_map(session, url, log=None, timeout=None):
    try:
        data = _get_json(
            session, url, "/api/v1/targets/metadata", log=log, timeout=timeout
        )
    except requests.HTTPError as exc:
        if log:
            log(f"Metadata unavailable: {exc}")
        return {}
    meta = {}
    for item in data or []:
        name = item.get("metric")
        if name and name not in meta:
            meta[name] = item
    return meta


def _build_selector(query, selector):
    selector = selector.strip() if selector else ""
    if selector.startswith("{") and selector.endswith("}"):
        selector = selector[1:-1].strip()
    label_part = f",{selector}" if selector else ""
    return f'{{__name__="{query}"{label_part}}}'


def _query(session, url, promql, log=None, timeout=None):
    data = _get_json(
        session,
        url,
        "/api/v1/query",
        params={"query": promql},
        log=log,
        timeout=timeout,
    )
    return data.get("result", [])


def _instant_query(session, url, query, selector, log=None, timeout=None):
    promql = _build_selector(query, selector)
    started = time.monotonic()
    result = _query(session, url, promql, log=log, timeout=timeout)
    return result, time.monotonic() - started


def _series_count(session, url, query, selector, log=None, timeout=None):
    promql = f"count({_build_selector(query, selector)})"
    started = time.monotonic()
    result = _query(session, url, promql, log=log, timeout=timeout)
    count = None
    if result:
        count = result[0].get("value", [None, None])[1]
    return count, time.monotonic() - started


def _label_values(session, url, metric, label, selector, log=None, timeout=None):
    match = _build_selector(metric, selector)
    data = _get_json(
        session,
        url,
        f"/api/v1/label/{label}/values",
        params={"match[]": match},
        log=log,
        timeout=timeout,
    )
    return data or []


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
    if any(row.get("error") for row in rows):
        table.add_column("Error")
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
        if any(r.get("error") for r in rows):
            cells.append(row.get("error", ""))
        table.add_row(*cells)
    console.print(table)


def _emit_jsonl(rows):
    for row in rows:
        print(json.dumps(row, ensure_ascii=True, sort_keys=True))


def _emit_profile_table(rows):
    show_type = any(row.get("type") for row in rows)
    show_unit = any(row.get("unit") for row in rows)
    show_series = any(str(row.get("series", "")).strip() for row in rows)
    show_samples = any(str(row.get("samples", "")).strip() for row in rows)
    show_min = any(row.get("min") is not None for row in rows)
    show_max = any(row.get("max") is not None for row in rows)
    show_avg = any(row.get("avg") is not None for row in rows)
    show_last = any(row.get("last") is not None for row in rows)
    show_last_age = any(
        (row.get("stale") is True)
        or (row.get("last_age") is not None and row.get("last_age") > 60)
        for row in rows
    )
    show_resets = any((row.get("resets") or 0) > 0 for row in rows)
    show_stale = any(row.get("stale") is not None for row in rows)
    show_label_keys = any(row.get("label_keys") for row in rows)
    show_group_by = any(row.get("group_by") for row in rows)
    show_sample_labels = any(row.get("sample_labels") for row in rows)
    show_label_values = any(row.get("label_values") for row in rows)
    show_error = any(row.get("error") for row in rows)
    show_stat = any(row.get("stat") for row in rows)

    table = Table(title="Metric Profiles")
    table.add_column("Metric")
    if show_type:
        table.add_column("Type")
    if show_unit:
        table.add_column("Unit")
    if show_series:
        table.add_column("Series")
    if show_samples:
        table.add_column("Samples")
    if show_stat:
        table.add_column("Stat")
    if show_resets:
        table.add_column("Resets")
    if show_stale:
        table.add_column("Stale")
    if show_min:
        table.add_column("Min")
    if show_max:
        table.add_column("Max")
    if show_avg:
        table.add_column("Avg")
    if show_last:
        table.add_column("Last")
    if show_last_age:
        table.add_column("Last Age s")
    if show_label_keys:
        table.add_column("Label Keys")
    if show_group_by:
        table.add_column("Group By")
    if show_sample_labels:
        table.add_column("Sample Labels")
    if show_label_values:
        table.add_column("Label Values")
    if show_error:
        table.add_column("Error")
    for row in rows:
        label_values = row.get("label_values") or {}
        label_values_str = "; ".join(
            f"{key}={','.join(values)}" for key, values in label_values.items()
        )
        cells = [row.get("metric", "")]
        if show_type:
            cells.append(row.get("type", ""))
        if show_unit:
            cells.append(row.get("unit", ""))
        if show_series:
            cells.append(str(row.get("series", "")))
        if show_samples:
            cells.append(str(row.get("samples", "")))
        if show_stat:
            cells.append(row.get("stat", ""))
        if show_resets:
            resets = row.get("resets")
            cells.append("" if resets is None else f"{resets:.0f}")
        if show_stale:
            stale = row.get("stale")
            if stale is None:
                cells.append("")
            else:
                cells.append("yes" if stale else "no")
        if show_min:
            cells.append("" if row.get("min") is None else f"{row['min']:.6g}")
        if show_max:
            cells.append("" if row.get("max") is None else f"{row['max']:.6g}")
        if show_avg:
            cells.append("" if row.get("avg") is None else f"{row['avg']:.6g}")
        if show_last:
            cells.append("" if row.get("last") is None else f"{row['last']:.6g}")
        if show_last_age:
            last_age = row.get("last_age")
            stale = row.get("stale") is True
            if last_age is None or (not stale and last_age <= 60):
                cells.append("")
            else:
                cells.append(f"{last_age:.0f}")
        if show_label_keys:
            cells.append(row.get("label_keys_compact", ""))
        if show_group_by:
            cells.append(row.get("group_by", ""))
        if show_sample_labels:
            cells.append(_format_labels(row.get("sample_labels", {})))
        if show_label_values:
            cells.append(label_values_str)
        if show_error:
            cells.append("ERR" if row.get("error") else "")
        table.add_row(*cells)
    console.print(table)


def _label_summary(rows, value_limit):
    counts = {}
    examples = {}
    for row in rows:
        labels = row.get("sample_labels") or {}
        for key, value in labels.items():
            if key == "__name__":
                continue
            counts.setdefault(key, 0)
            examples.setdefault(key, [])
        for key in set(labels.keys()):
            if key == "__name__":
                continue
            counts[key] += 1
        for key, value in labels.items():
            if key == "__name__":
                continue
            values = examples[key]
            if value not in values and len(values) < value_limit:
                values.append(str(value))
    summary = [
        {"label": key, "count": counts[key], "examples": examples[key]}
        for key in counts
    ]
    summary.sort(key=lambda item: item["count"], reverse=True)
    return summary


def _emit_label_summary_table(summary):
    table = Table(title="Label Summary")
    table.add_column("Label")
    table.add_column("Metrics")
    table.add_column("Examples")
    for item in summary:
        table.add_row(
            item["label"],
            str(item["count"]),
            ", ".join(item["examples"]),
        )
    console.print(table)


def _filter_names(names, regex, match):
    if regex:
        pattern = re.compile(regex)
        names = [name for name in names if pattern.search(name)]
    if match:
        needle = match.lower()
        names = [name for name in names if needle in name.lower()]
    return names


def _infer_type(name):
    if name.endswith("_bucket") or name.endswith("_sum") or name.endswith("_count"):
        return "histogram"
    if name.endswith("_total") or name.endswith("_created"):
        return "counter"
    return "gauge"


def _filter_label_keys(label_keys, mode, include, exclude):
    if include:
        return [key for key in label_keys if key in include and key not in exclude]
    if mode != "auto":
        return [key for key in label_keys if key not in exclude]
    noisy = {
        "__name__",
        "container",
        "endpoint",
        "host",
        "instance",
        "job",
        "pod",
        "prometheus",
        "receive",
        "tenant_id",
        "provider",
        "monitor_source",
        "k8s_cluster_name",
        "k8s_namespace_name",
        "namespace",
        "cluster",
        "infrastructure_provider",
    }
    return [key for key in label_keys if key not in noisy and key not in exclude]


def _parse_duration(value):
    if value is None:
        return None
    pattern = re.compile(r"^(\d+)([smhd])$")
    match = pattern.match(value.strip())
    if not match:
        raise click.ClickException(f"Invalid duration: {value}")
    amount = int(match.group(1))
    unit = match.group(2)
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _range_query(session, url, promql, start, end, step, log=None, timeout=None):
    data = _get_json(
        session,
        url,
        "/api/v1/query_range",
        params={"query": promql, "start": start, "end": end, "step": step},
        log=log,
        timeout=timeout,
    )
    return data.get("result", [])


def _summarize_matrix(result, end_ts):
    series_count = len(result)
    sample_count = 0
    min_v = None
    max_v = None
    sum_v = 0.0
    last_v = None
    last_ts = None
    for series in result:
        values = series.get("values") or []
        for ts, val in values:
            sample_count += 1
            v = float(val)
            if not (v == v) or v in (float("inf"), float("-inf")):
                continue
            min_v = v if min_v is None else min(min_v, v)
            max_v = v if max_v is None else max(max_v, v)
            sum_v += v
            if last_ts is None or ts > last_ts:
                last_ts = ts
                last_v = v
    avg_v = sum_v / sample_count if sample_count else None
    last_age = end_ts - last_ts if last_ts is not None else None
    return {
        "series": series_count,
        "samples": sample_count,
        "min": min_v,
        "max": max_v,
        "avg": avg_v,
        "last": last_v,
        "last_age": last_age,
    }


def _summarize_resets(result):
    total = 0.0
    for series in result:
        values = series.get("values") or []
        if values:
            total += float(values[-1][1])
    return total


def _compact_label_keys(keys, limit):
    if not limit or len(keys) <= limit:
        return ",".join(keys)
    shown = ",".join(keys[:limit])
    return f"{shown},+{len(keys) - limit}"


def _parse_selector_keys(selector):
    if not selector:
        return set()
    selector = selector.strip()
    if selector.startswith("{") and selector.endswith("}"):
        selector = selector[1:-1]
    keys = set()
    for chunk in selector.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        for op in ("=~", "!~", "=", "!="):
            if op in chunk:
                keys.add(chunk.split(op, 1)[0].strip())
                break
    return keys


def _grouping_candidates(label_keys, selector_keys):
    noisy = {
        "le",
        "status",
        "method",
        "path",
        "stage",
        "error_type",
    }
    return [key for key in label_keys if key not in selector_keys and key not in noisy]


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
    "--fail-fast/--continue",
    default=False,
    show_default=True,
    help="Abort on the first query error.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel workers for queries.",
)
@click.pass_context
def sample_metrics(ctx, sample, stats, selector, show_latency, fail_fast, workers):
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
            try:
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
            except requests.RequestException as exc:
                if fail_fast:
                    raise
                row["error"] = str(exc)
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


@main.command("profile")
@click.option(
    "--selector",
    help='Label selector to apply (e.g. cluster="prod",namespace=~"kube-.*").',
)
@click.option(
    "--label-mode",
    type=click.Choice(["all", "auto"]),
    default="auto",
    show_default=True,
    help="Which label keys to show in output.",
)
@click.option(
    "--label-include",
    "label_include",
    multiple=True,
    help="Force-include label keys (repeatable).",
)
@click.option(
    "--label-exclude",
    "label_exclude",
    multiple=True,
    help="Exclude label keys (repeatable).",
)
@click.option(
    "--label-keys-max",
    type=int,
    default=4,
    show_default=True,
    help="Max label keys to display before truncating.",
)
@click.option(
    "--label-keys-count/--no-label-keys-count",
    default=False,
    show_default=True,
    help="Show label key count instead of listing.",
)
@click.option(
    "--sample-labels/--no-sample-labels",
    "show_sample_labels",
    default=False,
    show_default=True,
    help="Include sample labels in the output table.",
)
@click.option(
    "--labels-summary/--no-labels-summary",
    default=True,
    show_default=True,
    help="Show a summary table of common labels with example values.",
)
@click.option(
    "--labels-summary-limit",
    type=int,
    default=3,
    show_default=True,
    help="Max example values per label in the summary table.",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Compact output (hide sample labels, reduce label keys, hide samples).",
)
@click.option(
    "--group-by",
    "group_by",
    multiple=True,
    help="Group quantiles/rates by these labels (repeatable).",
)
@click.option(
    "--label",
    "labels",
    multiple=True,
    help="Label keys to sample values for (repeatable).",
)
@click.option(
    "--label-limit",
    type=int,
    default=5,
    show_default=True,
    help="Max label values per label.",
)
@click.option(
    "--metadata/--no-metadata",
    default=True,
    show_default=True,
    help="Fetch metric metadata (type, unit, help).",
)
@click.option(
    "--stats/--no-stats",
    default=True,
    show_default=True,
    help="Collect range statistics (min/max/avg/last).",
)
@click.option(
    "--quantile",
    "quantiles",
    multiple=True,
    type=float,
    help="Quantiles for histogram buckets (repeatable). Default: 0.95",
)
@click.option(
    "--stale",
    "stale_window",
    default="10m",
    show_default=True,
    help="Staleness window for 'last_age' comparison.",
)
@click.option(
    "--resets/--no-resets",
    default=True,
    show_default=True,
    help="Collect counter resets over the range window.",
)
@click.option(
    "--range",
    "range_window",
    default="1h",
    show_default=True,
    help="Range window for statistics (e.g. 30m, 6h).",
)
@click.option(
    "--step",
    default="60s",
    show_default=True,
    help="Query step for statistics (e.g. 30s, 5m).",
)
@click.option(
    "--fail-fast/--continue",
    default=False,
    show_default=True,
    help="Abort on the first query error.",
)
@click.option(
    "--workers",
    type=int,
    default=8,
    show_default=True,
    help="Number of parallel workers for queries.",
)
@click.pass_context
def profile_metrics(
    ctx,
    selector,
    label_mode,
    label_include,
    label_exclude,
    label_keys_max,
    label_keys_count,
    show_sample_labels,
    labels_summary,
    labels_summary_limit,
    compact,
    group_by,
    labels,
    label_limit,
    metadata,
    stats,
    quantiles,
    range_window,
    step,
    stale_window,
    resets,
    fail_fast,
    workers,
):
    """Profile metrics for dashboard/alert planning."""
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

    meta = {}
    if metadata:
        meta = _metadata_map(
            session, ctx.obj["url"], log=log, timeout=ctx.obj["timeout"]
        )
    range_seconds = _parse_duration(range_window) if stats else None
    step_seconds = _parse_duration(step) if stats else None
    stale_seconds = _parse_duration(stale_window) if stats else None
    quantiles = quantiles or (0.95,)
    group_by = tuple(group_by)
    selector_keys = _parse_selector_keys(selector)
    if compact:
        label_keys_max = min(label_keys_max, 2)

    def _fetch_row(idx, name):
        if log:
            log(f"Metric {idx}/{total}: {name}")
        local_session = requests.Session()
        meta_item = meta.get(name, {})
        row = {
            "metric": name,
            "type": meta_item.get("type") or _infer_type(name),
            "unit": meta_item.get("unit", ""),
            "help": meta_item.get("help", ""),
            "series": "",
            "label_keys": [],
            "label_keys_compact": "",
            "group_by": "",
            "sample_labels": {},
            "label_values": {},
            "samples": "",
            "min": None,
            "max": None,
            "avg": None,
            "last": None,
            "last_age": None,
            "stat": "",
            "resets": None,
            "stale": None,
        }
        try:
            sample_result, _ = _instant_query(
                local_session,
                ctx.obj["url"],
                name,
                selector,
                log=log,
                timeout=ctx.obj["timeout"],
            )
            sample_labels = sample_result[0].get("metric", {}) if sample_result else {}
            row["sample_labels"] = sample_labels
            label_keys = sorted(
                [key for key in sample_labels.keys() if key != "__name__"]
            )
            filtered_keys = _filter_label_keys(
                label_keys, label_mode, label_include, label_exclude
            )
            row["label_keys"] = filtered_keys
            if label_keys_count:
                row["label_keys_compact"] = str(len(filtered_keys))
            else:
                row["label_keys_compact"] = _compact_label_keys(
                    filtered_keys, label_keys_max
                )
            row["group_by"] = _compact_label_keys(
                _grouping_candidates(filtered_keys, selector_keys), 3
            )
            series_count, _ = _series_count(
                local_session,
                ctx.obj["url"],
                name,
                selector,
                log=log,
                timeout=ctx.obj["timeout"],
            )
            row["series"] = series_count or ""
            if compact:
                row["samples"] = ""
            if stats and range_seconds and step_seconds:
                end_ts = time.time()
                start_ts = end_ts - range_seconds
                metric_type = row["type"]
                if metric_type == "counter":
                    promql = f"rate({_build_selector(name, selector)}[{range_window}])"
                    row["stat"] = "rate"
                    matrix = _range_query(
                        local_session,
                        ctx.obj["url"],
                        promql,
                        start_ts,
                        end_ts,
                        step_seconds,
                        log=log,
                        timeout=ctx.obj["timeout"],
                    )
                    stats_row = _summarize_matrix(matrix, end_ts)
                    row.update(stats_row)
                    if resets:
                        resets_query = (
                            f"sum(resets({_build_selector(name, selector)}"
                            f"[{range_window}]))"
                        )
                        resets_matrix = _range_query(
                            local_session,
                            ctx.obj["url"],
                            resets_query,
                            start_ts,
                            end_ts,
                            step_seconds,
                            log=log,
                            timeout=ctx.obj["timeout"],
                        )
                        row["resets"] = _summarize_resets(resets_matrix)
                elif metric_type == "histogram" and name.endswith("_bucket"):
                    q = quantiles[0]
                    group = ", ".join(("le",) + group_by) if group_by else "le"
                    promql = (
                        f"histogram_quantile({q}, "
                        f"sum(rate({_build_selector(name, selector)}[{range_window}])) by ({group}))"
                    )
                    row["stat"] = f"p{int(q * 100)}"
                    matrix = _range_query(
                        local_session,
                        ctx.obj["url"],
                        promql,
                        start_ts,
                        end_ts,
                        step_seconds,
                        log=log,
                        timeout=ctx.obj["timeout"],
                    )
                    stats_row = _summarize_matrix(matrix, end_ts)
                    row.update(stats_row)
                elif metric_type == "histogram":
                    promql = f"rate({_build_selector(name, selector)}[{range_window}])"
                    row["stat"] = "rate"
                    matrix = _range_query(
                        local_session,
                        ctx.obj["url"],
                        promql,
                        start_ts,
                        end_ts,
                        step_seconds,
                        log=log,
                        timeout=ctx.obj["timeout"],
                    )
                    stats_row = _summarize_matrix(matrix, end_ts)
                    row.update(stats_row)
                else:
                    row["stat"] = "gauge"
                    matrix = _range_query(
                        local_session,
                        ctx.obj["url"],
                        _build_selector(name, selector),
                        start_ts,
                        end_ts,
                        step_seconds,
                        log=log,
                        timeout=ctx.obj["timeout"],
                    )
                    stats_row = _summarize_matrix(matrix, end_ts)
                    row.update(stats_row)
                if stale_seconds is not None and row["last_age"] is not None:
                    row["stale"] = row["last_age"] > stale_seconds
            label_values = {}
            for label in labels:
                values = _label_values(
                    local_session,
                    ctx.obj["url"],
                    name,
                    label,
                    selector,
                    log=log,
                    timeout=ctx.obj["timeout"],
                )
                label_values[label] = values[:label_limit]
            row["label_values"] = label_values
        except requests.RequestException as exc:
            if fail_fast:
                raise
            row["error"] = str(exc)
            if log:
                log(f"Error for {name}: {exc}")
        return idx, row

    rows = [None] * len(names)
    total = len(names)
    with progress:
        task = progress.add_task("Profiling metrics", total=total)
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
        _emit_profile_table(rows)
        if labels_summary:
            summary = _label_summary(rows, labels_summary_limit)
            _emit_label_summary_table(summary)
    else:
        _emit_jsonl(rows)


if __name__ == "__main__":
    main()
