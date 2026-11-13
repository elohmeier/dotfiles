"""Switch the shared chezmoi theme without running unrelated hooks."""

import json
import subprocess
from pathlib import Path

import rich_click as click
import tomlkit

THEMES = ("tokyonight_day", "tokyonight_night", "cyberdream_light", "cyberdream")


@click.command()
@click.argument("name", type=click.Choice(THEMES), required=False)
@click.option("--dry-run", is_flag=True, help="Preview without changing configuration.")
def main(name: str | None, dry_run: bool) -> None:
    """Show the current theme or switch themed dotfiles to NAME."""
    chezmoi = ["chezmoi", "--skip-secrets"]
    config_path = Path(
        subprocess.check_output(
            [*chezmoi, "execute-template", "{{ .chezmoi.configFile }}"], text=True
        ).strip()
    )
    config = tomlkit.parse(config_path.read_text())
    if name is None:
        click.echo(config["data"]["theme"])
        return

    managed = subprocess.check_output(
        [
            *chezmoi,
            "managed",
            "--include=files,scripts",
            "--path-style=source-absolute",
        ],
        text=True,
    ).splitlines()
    targets = [
        path
        for path in map(Path, managed)
        if path.suffix == ".tmpl" and "theme" in path.read_text()
    ]
    if not dry_run:
        config["data"]["theme"] = name
        config_path.write_text(tomlkit.dumps(config))
    if targets:
        subprocess.run(
            [
                *chezmoi,
                "--override-data",
                json.dumps({"theme": name}),
                "apply",
                "--source-path",
                *(["--dry-run"] if dry_run else []),
                *map(str, targets),
            ],
            check=True,
        )
    click.echo(f"{'Would set' if dry_run else 'Set'} theme to {name}.")


if __name__ == "__main__":
    main()
