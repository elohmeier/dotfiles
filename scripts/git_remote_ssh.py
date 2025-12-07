import subprocess

import rich_click as click
from rich.console import Console

console = Console(stderr=True)


@click.command()
@click.argument("remote", default="origin")
def main(remote: str):
    result = subprocess.run(
        ["git", "remote", "get-url", remote],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Remote '{remote}' not found")

    url = result.stdout.strip()

    # https://github.com/user/repo.git -> git@github.com:user/repo.git
    if not url.startswith("https://github.com/"):
        raise SystemExit(f"Not a GitHub HTTPS URL: {url}")

    path = url.removeprefix("https://github.com/")
    ssh_url = f"git@github.com:{path}"

    subprocess.run(["git", "remote", "set-url", remote, ssh_url], check=True)
    console.print(f"[green]{remote}[/]: {url} → {ssh_url}")
