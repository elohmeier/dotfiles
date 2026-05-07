"""Console viewer for Grafana dashboard JSON files."""

from __future__ import annotations

import json
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import rich_click as click
from rich.console import Console
from rich.markup import escape

JSON = dict[str, Any]

console = Console()


@dataclass
class Query:
    ref_id: str
    datasource: str
    text: str
    legend: str = ""
    hidden: bool = False
    mode: str = ""


@dataclass
class Panel:
    key: str
    title: str
    plugin: str
    description: str = ""
    queries: list[Query] = field(default_factory=list)
    layout: dict[str, Any] = field(default_factory=dict)


@dataclass
class Row:
    title: str
    panels: list[Panel] = field(default_factory=list)
    collapsed: bool = False


@click.command()
@click.argument(
    "dashboard",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--layout",
    "show_layout",
    is_flag=True,
    help="Include grid coordinates and panel dimensions.",
)
@click.option(
    "--no-queries",
    is_flag=True,
    help="Show structure and metadata without query bodies.",
)
@click.option(
    "--queries-only",
    is_flag=True,
    help="Print only panel titles and queries.",
)
@click.option(
    "--show-hidden",
    is_flag=True,
    help="Include hidden queries.",
)
@click.option(
    "--max-query-lines",
    type=int,
    default=18,
    show_default=True,
    help="Maximum lines to print per query before truncating.",
)
@click.option(
    "--width",
    type=int,
    default=0,
    help="Wrap output to this width instead of the terminal width.",
)
def main(
    dashboard: Path,
    show_layout: bool,
    no_queries: bool,
    queries_only: bool,
    show_hidden: bool,
    max_query_lines: int,
    width: int,
) -> None:
    """Print a readable outline of a Grafana dashboard JSON file."""
    try:
        data = load_dashboard(dashboard)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        console.print(f"[red]error:[/] {escape(str(exc))}", soft_wrap=True)
        sys.exit(1)

    width = width or console.size.width
    width = max(72, width)

    rows, loose_panels = collect_structure(data)
    panels = [panel for row in rows for panel in row.panels] + loose_panels

    if queries_only:
        print_queries(panels, show_hidden, max_query_lines, width)
        return

    print_metadata(data, panels, rows)
    print_variables(data, width)
    print_annotations(data, width)
    print_structure(
        rows, loose_panels, show_layout, no_queries, show_hidden, max_query_lines, width
    )


def load_dashboard(path: Path) -> JSON:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and isinstance(data.get("dashboard"), dict):
        data = data["dashboard"]
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a Grafana dashboard object")
    return data


def collect_structure(dashboard: JSON) -> tuple[list[Row], list[Panel]]:
    if isinstance(dashboard.get("elements"), dict):
        return collect_schema_v2(dashboard)
    return collect_legacy(dashboard)


def collect_schema_v2(dashboard: JSON) -> tuple[list[Row], list[Panel]]:
    elements = dashboard.get("elements") or {}
    panels_by_key = {
        key: panel_from_v2(key, value)
        for key, value in elements.items()
        if isinstance(value, dict) and value.get("kind") == "Panel"
    }
    used: set[str] = set()
    rows: list[Row] = []

    layout = dashboard.get("layout") or {}
    if layout.get("kind") == "RowsLayout":
        for row_data in (layout.get("spec") or {}).get("rows") or []:
            spec = row_data.get("spec") or {}
            row = Row(
                title=str(spec.get("title") or "(untitled row)"),
                collapsed=bool(spec.get("collapse")),
            )
            for item in grid_items(spec.get("layout") or {}):
                name = element_name(item)
                panel = panels_by_key.get(name)
                if not panel:
                    continue
                panel.layout = item.get("spec") or {}
                row.panels.append(panel)
                used.add(name)
            rows.append(row)
    elif layout:
        row = Row(title="Dashboard")
        for item in grid_items(layout):
            name = element_name(item)
            panel = panels_by_key.get(name)
            if not panel:
                continue
            panel.layout = item.get("spec") or {}
            row.panels.append(panel)
            used.add(name)
        if row.panels:
            rows.append(row)

    loose = [panel for key, panel in sorted(panels_by_key.items()) if key not in used]
    return rows, loose


def panel_from_v2(key: str, element: JSON) -> Panel:
    spec = element.get("spec") or {}
    viz = spec.get("vizConfig") or {}
    panel = Panel(
        key=key,
        title=str(spec.get("title") or key),
        plugin=str(viz.get("group") or viz.get("kind") or "panel"),
        description=clean_text(spec.get("description")),
    )
    data = spec.get("data") or {}
    query_objects: list[JSON] = []
    if data.get("kind") == "PanelQuery":
        query_objects = [data]
    else:
        query_objects = (data.get("spec") or {}).get("queries") or []
    panel.queries = [
        query_from_v2(item) for item in query_objects if isinstance(item, dict)
    ]
    return panel


def query_from_v2(item: JSON) -> Query:
    spec = item.get("spec") or {}
    query = spec.get("query") or {}
    query_spec = query.get("spec") or {}
    text = first_text(
        query_spec,
        "expr",
        "rawSql",
        "rawSQL",
        "sql",
        "query",
        "__legacyStringValue",
    )
    if not text:
        text = compact_json(query_spec)
    return Query(
        ref_id=str(spec.get("refId") or "?"),
        datasource=datasource_name(query.get("datasource"))
        or str(query.get("group") or query.get("kind") or ""),
        text=clean_query(text),
        legend=str(query_spec.get("legendFormat") or query_spec.get("alias") or ""),
        hidden=bool(spec.get("hidden")),
        mode=query_mode(query_spec),
    )


def collect_legacy(dashboard: JSON) -> tuple[list[Row], list[Panel]]:
    rows: list[Row] = []
    loose: list[Panel] = []
    current = Row(title="Dashboard")
    saw_explicit_row = False

    for raw in dashboard.get("panels") or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("type") == "row":
            saw_explicit_row = True
            if current.panels:
                rows.append(current)
            current = Row(
                title=str(raw.get("title") or "(untitled row)"),
                collapsed=bool(raw.get("collapsed")),
            )
            for child in raw.get("panels") or []:
                panel = panel_from_legacy(child)
                current.panels.append(panel)
            if current.panels and raw.get("collapsed"):
                rows.append(current)
                current = Row(title="Dashboard")
            continue
        panel = panel_from_legacy(raw)
        if rows or current.title != "Dashboard":
            current.panels.append(panel)
        else:
            loose.append(panel)

    if current.panels:
        rows.append(current)
    if not saw_explicit_row and loose:
        loose = sorted(loose, key=panel_layout_sort_key)
        return [Row(title="Dashboard", panels=loose)], []
    return rows, loose


def panel_from_legacy(raw: JSON) -> Panel:
    panel = Panel(
        key=str(raw.get("id") or raw.get("uid") or "?"),
        title=str(raw.get("title") or "(untitled panel)"),
        plugin=str(raw.get("type") or "panel"),
        description=clean_text(raw.get("description")),
        layout=raw.get("gridPos") or {},
    )
    panel.queries = [
        query_from_legacy(item)
        for item in raw.get("targets") or []
        if isinstance(item, dict)
    ]
    return panel


def panel_layout_sort_key(panel: Panel) -> tuple[int, int, str]:
    return (
        int(panel.layout.get("y") or 0),
        int(panel.layout.get("x") or 0),
        panel.key,
    )


def query_from_legacy(item: JSON) -> Query:
    text = first_text(item, "expr", "rawSql", "rawSQL", "sql", "query")
    if not text and item.get("measurement"):
        text = influx_summary(item)
    if not text:
        text = compact_json(
            {key: value for key, value in item.items() if key not in {"datasource"}}
        )
    return Query(
        ref_id=str(item.get("refId") or "?"),
        datasource=datasource_name(item.get("datasource")),
        text=clean_query(text),
        legend=str(item.get("legendFormat") or item.get("alias") or ""),
        hidden=bool(item.get("hide")),
        mode=query_mode(item),
    )


def grid_items(layout: JSON) -> list[JSON]:
    if not isinstance(layout, dict):
        return []
    kind = layout.get("kind")
    spec = layout.get("spec") or {}
    if kind in {"GridLayout", "AutoGridLayout"}:
        items = [item for item in spec.get("items") or [] if isinstance(item, dict)]
        return sorted(
            items,
            key=lambda item: (
                (item.get("spec") or {}).get("y", 0),
                (item.get("spec") or {}).get("x", 0),
            ),
        )
    if kind == "RowsLayout":
        items = []
        for row in spec.get("rows") or []:
            items.extend(grid_items((row.get("spec") or {}).get("layout") or {}))
        return items
    return []


def element_name(item: JSON) -> str:
    spec = item.get("spec") or {}
    element = spec.get("element") or {}
    return str(element.get("name") or "")


def print_metadata(dashboard: JSON, panels: list[Panel], rows: list[Row]) -> None:
    title = dashboard.get("title") or "(untitled dashboard)"
    console.print(f"[bold cyan]# {escape(str(title))}[/]")
    description = clean_text(dashboard.get("description"))
    if description:
        console.print(escape(description))

    tags = dashboard.get("tags") or []
    if tags:
        console.print(f"[dim]Tags:[/] {escape(', '.join(map(str, tags)))}")

    time_settings = dashboard.get("timeSettings") or {}
    legacy_time = dashboard.get("time") or {}
    time_from = time_settings.get("from") or legacy_time.get("from")
    time_to = time_settings.get("to") or legacy_time.get("to")
    refresh = time_settings.get("autoRefresh") or dashboard.get("refresh")
    timezone = time_settings.get("timezone") or dashboard.get("timezone")
    bits = []
    if time_from or time_to:
        bits.append(f"time {time_from or '?'} to {time_to or '?'}")
    if refresh:
        bits.append(f"refresh {refresh}")
    if timezone:
        bits.append(f"timezone {timezone}")
    if bits:
        console.print(f"[dim]Settings:[/] {escape('; '.join(bits))}")

    query_count = sum(len(panel.queries) for panel in panels)
    summary = ", ".join(
        [
            plural(len(rows), "row"),
            plural(len(panels), "panel"),
            plural(query_count, "query", "queries"),
        ]
    )
    console.print(f"[dim]Structure:[/] {summary}")
    console.print()


def print_variables(dashboard: JSON, width: int) -> None:
    variables = dashboard.get("variables")
    if variables is None:
        variables = (dashboard.get("templating") or {}).get("list") or []
    if not variables:
        return
    console.print("[bold magenta]## Variables[/]")
    for variable in variables:
        if not isinstance(variable, dict):
            continue
        if "spec" in variable:
            kind = str(variable.get("kind") or "Variable")
            spec = variable.get("spec") or {}
        else:
            kind = str(variable.get("type") or "Variable")
            spec = variable
        name = spec.get("name") or "(unnamed)"
        label = spec.get("label") or ""
        multi = flag(spec.get("multi"), "multi")
        include_all = flag(spec.get("includeAll"), "all")
        query = variable_query(spec)
        suffix = ", ".join(
            bit for bit in [kind, label and f"label={label}", multi, include_all] if bit
        )
        console.print(f"- [green]${escape(str(name))}[/] ({escape(suffix)})")
        if query:
            print_wrapped(query, indent="  query: ", width=width)
    console.print()


def print_annotations(dashboard: JSON, width: int) -> None:
    annotations = dashboard.get("annotations")
    if isinstance(annotations, dict):
        annotations = annotations.get("list") or []
    if not annotations:
        return
    visible = []
    for annotation in annotations:
        spec = annotation.get("spec") if isinstance(annotation, dict) else None
        spec = spec or annotation
        if isinstance(spec, dict) and not spec.get("builtIn"):
            visible.append(spec)
    if not visible:
        return
    console.print("[bold magenta]## Annotations[/]")
    for spec in visible:
        console.print(f"- {escape(str(spec.get('name') or '(unnamed annotation)'))}")
        query = variable_query(spec)
        if query:
            print_wrapped(query, indent="  query: ", width=width)
    console.print()


def print_structure(
    rows: list[Row],
    loose_panels: list[Panel],
    show_layout: bool,
    no_queries: bool,
    show_hidden: bool,
    max_query_lines: int,
    width: int,
) -> None:
    console.print("[bold magenta]## Layout[/]")
    for row in rows:
        state = " [yellow](collapsed)[/]" if row.collapsed else ""
        console.print(f"[bold yellow]### {escape(row.title)}[/]{state}")
        for panel in row.panels:
            print_panel(
                panel, show_layout, no_queries, show_hidden, max_query_lines, width
            )
        console.print()
    if loose_panels:
        console.print("[bold yellow]### Panels[/]")
        for panel in loose_panels:
            print_panel(
                panel, show_layout, no_queries, show_hidden, max_query_lines, width
            )
        console.print()


def print_panel(
    panel: Panel,
    show_layout: bool,
    no_queries: bool,
    show_hidden: bool,
    max_query_lines: int,
    width: int,
) -> None:
    hidden_count = sum(1 for query in panel.queries if query.hidden)
    shown_queries = [
        query for query in panel.queries if show_hidden or not query.hidden
    ]
    query_label = plural(len(shown_queries), "query", "queries")
    if hidden_count and not show_hidden:
        query_label += f", {hidden_count} hidden"
    layout = (
        f" [dim]{escape(format_layout(panel.layout))}[/]"
        if show_layout and panel.layout
        else ""
    )
    console.print(
        f"- [cyan]\\[{escape(panel.plugin)}][/] [bold]{escape(panel.title)}[/] [dim]({query_label})[/]{layout}"
    )
    if panel.description:
        print_wrapped(panel.description, indent="  description: ", width=width)
    if no_queries:
        return
    for query in shown_queries:
        print_query(query, width, max_query_lines, indent="  ")


def print_queries(
    panels: list[Panel], show_hidden: bool, max_query_lines: int, width: int
) -> None:
    for panel in panels:
        queries = [query for query in panel.queries if show_hidden or not query.hidden]
        if not queries:
            continue
        console.print(
            f"[bold magenta]## {escape(panel.title)}[/] [dim]\\[{escape(panel.plugin)}][/]"
        )
        for query in queries:
            print_query(query, width, max_query_lines, indent="")
        console.print()


def print_query(query: Query, width: int, max_lines: int, indent: str) -> None:
    hidden = " [red]hidden[/]" if query.hidden else ""
    mode = f" [dim]{escape(query.mode)}[/]" if query.mode else ""
    datasource = (
        f" [dim]datasource={escape(query.datasource)}[/]" if query.datasource else ""
    )
    legend = f" [dim]legend={escape(query.legend)}[/]" if query.legend else ""
    console.print(
        f"{indent}[green]{escape(query.ref_id)}:[/]{hidden}{mode}{datasource}{legend}"
    )
    print_block(query.text, indent=indent + "  ", width=width, max_lines=max_lines)


def print_wrapped(text: str, indent: str, width: int) -> None:
    subsequent = " " * len(indent)
    console.print(
        escape(
            textwrap.fill(
                text, width=width, initial_indent=indent, subsequent_indent=subsequent
            )
        )
    )


def print_block(text: str, indent: str, width: int, max_lines: int) -> None:
    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if len(raw_line) + len(indent) <= width:
            lines.append(raw_line)
        else:
            lines.extend(
                textwrap.wrap(
                    raw_line,
                    width=max(20, width - len(indent)),
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
    truncated = max_lines > 0 and len(lines) > max_lines
    if truncated:
        lines = lines[:max_lines]
    for line in lines:
        console.print(f"{indent}{escape(line)}")
    if truncated:
        console.print(f"{indent}[dim]... ({max_lines} wrapped lines shown)[/]")


def variable_query(spec: JSON) -> str:
    query = spec.get("query")
    if isinstance(query, str):
        return clean_query(query)
    if isinstance(query, dict):
        nested = query.get("spec") if isinstance(query.get("spec"), dict) else query
        text = first_text(nested, "__legacyStringValue", "expr", "rawSql", "query")
        if text:
            return clean_query(text)
    options = spec.get("options")
    if isinstance(options, list) and options:
        values = [
            str(option.get("text") if isinstance(option, dict) else option)
            for option in options[:8]
        ]
        suffix = " ..." if len(options) > len(values) else ""
        return "options: " + ", ".join(values) + suffix
    return ""


def first_text(data: JSON, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def datasource_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("uid") or value.get("name") or value.get("type") or "")
    return ""


def query_mode(data: JSON) -> str:
    bits = []
    if data.get("instant"):
        bits.append("instant")
    if data.get("range") is False:
        bits.append("no-range")
    if data.get("format"):
        bits.append(str(data["format"]))
    return ", ".join(bits)


def influx_summary(item: JSON) -> str:
    measurement = item.get("measurement")
    policy = item.get("policy")
    parts = [f"measurement: {measurement}"]
    if policy:
        parts.append(f"policy: {policy}")
    if item.get("tags"):
        parts.append("tags: " + compact_json(item["tags"]))
    if item.get("groupBy"):
        parts.append("group by: " + compact_json(item["groupBy"]))
    if item.get("select"):
        parts.append("select: " + compact_json(item["select"]))
    return "\n".join(parts)


def clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def clean_query(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def flag(value: Any, label: str) -> str:
    return label if value else ""


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural_form or singular + 's'}"


def format_layout(layout: JSON) -> str:
    if {"x", "y", "width", "height"} <= layout.keys():
        return f"grid x={layout['x']} y={layout['y']} w={layout['width']} h={layout['height']}"
    if {"x", "y", "w", "h"} <= layout.keys():
        return f"grid x={layout['x']} y={layout['y']} w={layout['w']} h={layout['h']}"
    return compact_json(layout)


if __name__ == "__main__":
    main()
