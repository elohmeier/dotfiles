from urllib.parse import parse_qsl, urlsplit

import rich_click as click
from rich.console import Console
from rich.table import Table
from rich.text import Text


@click.command()
@click.argument("url")
def main(url: str) -> None:
    """Inspect URL components and decoded query parameters without fetching it."""
    parts = urlsplit(url)
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column(overflow="fold")
    table.add_row("original", Text(url))
    for name in (
        "scheme",
        "username",
        "password",
        "hostname",
        "port",
        "path",
        "query",
        "fragment",
    ):
        value = getattr(parts, name)
        if value is not None and value != "":
            table.add_row(name, Text(str(value)))
        if name == "query":
            for key, value in parse_qsl(parts.query, keep_blank_values=True):
                table.add_row(Text(f"  {key}"), Text(value))
    Console().print(table)


if __name__ == "__main__":
    main()
