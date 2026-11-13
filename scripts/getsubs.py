"""Download a video's subtitles as plain text."""

import html
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import rich_click as click


def transcript(vtt: str) -> str:
    lines = []
    for block in re.split(r"\r?\n\s*\r?\n", vtt):
        cue = block.splitlines()
        for index, line in enumerate(cue):
            if " --> " in line:
                text = html.unescape(
                    re.sub(r"<[^>]+>", "", "\n".join(cue[index + 1 :]))
                )
                for line in text.splitlines():
                    line = " ".join(line.split())
                    if line and (not lines or line != lines[-1]):
                        lines.append(line)
                break
    return "\n".join(lines)


@click.command()
@click.argument("url")
@click.option("--lang", default="en", show_default=True, help="Subtitle language code.")
def main(url: str, lang: str) -> None:
    """Print subtitles for URL, preferring official captions over automatic ones."""
    with TemporaryDirectory(prefix="getsubs-") as directory:
        for flags in (
            ("--write-subs", "--no-write-auto-subs"),
            ("--write-auto-subs", "--no-write-subs"),
        ):
            subprocess.run(
                [
                    "yt-dlp",
                    "--skip-download",
                    "--no-playlist",
                    "--quiet",
                    *flags,
                    "--sub-langs",
                    lang,
                    "--sub-format",
                    "vtt",
                    "--output",
                    str(Path(directory) / "%(id)s.%(ext)s"),
                    "--",
                    url,
                ],
                stdout=sys.stderr,
                check=True,
            )
            if subtitles := sorted(Path(directory).glob("*.vtt")):
                click.echo(transcript(subtitles[0].read_text()))
                return
    raise click.ClickException(f"No {lang} subtitles found.")


if __name__ == "__main__":
    main()
