import subprocess
from pathlib import Path

import rich_click as click


@click.command()
@click.argument(
    "output", type=click.Path(path_type=Path, dir_okay=False), default="staged.patch"
)
def main(output: Path):
    """Export all staged changes, including binary files, to OUTPUT.

    OUTPUT defaults to staged.patch. Existing files are never overwritten.
    """
    patch = subprocess.check_output(
        [
            "git",
            "diff",
            "--cached",
            "--binary",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--no-relative",
            "--default-prefix",
            "--submodule=short",
        ]
    )
    if not patch:
        raise click.ClickException("No staged changes to export.")

    output = output.expanduser().absolute()
    with click.open_file(output, "xb", lazy=True) as file:
        file.write(patch)
    click.echo(f"Saved staged changes to {output}")


if __name__ == "__main__":
    main()
