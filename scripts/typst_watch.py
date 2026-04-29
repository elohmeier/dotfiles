"""Watch a Typst file, compile to PNG, and display via Kitty graphics protocol."""

import base64
import fcntl
import glob as globmod
import io
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
from collections.abc import Sequence
from pathlib import Path

import rich_click as click
from PIL import Image
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

_typst_bin = shutil.which("typst")
if not _typst_bin:
    raise SystemExit("typst is required for typst-watch")
TYPST_BIN = _typst_bin


def get_terminal_size() -> tuple[int, int, int, int]:
    try:
        buf = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
        rows, cols, xpx, ypx = struct.unpack("HHHH", buf)
    except OSError:
        sz = shutil.get_terminal_size()
        cols, rows, xpx, ypx = sz.columns, sz.lines, 0, 0
    return cols, rows, xpx or cols * 8, ypx or rows * 16


def kitty_display(png_data: bytes, *, cols: int, rows: int) -> None:
    b64 = base64.standard_b64encode(png_data).decode()
    chunks = [b64[i : i + 4096] for i in range(0, len(b64), 4096)]
    for i, chunk in enumerate(chunks):
        more = 0 if i == len(chunks) - 1 else 1
        prefix = f"a=T,f=100,c={cols},r={rows}," if i == 0 else ""
        sys.stdout.write(f"\033_G{prefix}m={more};{chunk}\033\\")


def compose_row(images: Sequence[Image.Image], gap_px: int = 30) -> Image.Image:
    if len(images) == 1:
        return images[0]
    height = max(img.height for img in images)
    resized = [
        img.resize(
            (int(img.width * height / img.height), height), Image.Resampling.LANCZOS
        )
        for img in images
    ]
    width = sum(img.width for img in resized) + gap_px * (len(resized) - 1)
    combined = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = 0
    for img in resized:
        combined.paste(img, (x, 0))
        x += img.width + gap_px
    return combined


def image_to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def display_pages(pages: list[Path]) -> None:
    if not pages:
        return

    term_cols, term_rows, term_xpx, term_ypx = get_terminal_size()
    cell_w = term_xpx / term_cols
    cell_h = term_ypx / term_rows

    images = [Image.open(p) for p in pages]
    rows = (
        [compose_row(images[i : i + 2]) for i in range(0, len(images), 2)]
        if len(images) >= 2 and term_xpx > term_ypx
        else images
    )

    sys.stdout.write("\033_Ga=d;\033\\\033[2J\033[H")
    sys.stdout.flush()

    for img in rows:
        aspect = img.height / img.width
        display_cols = term_cols
        display_rows = int(display_cols * cell_w * aspect / cell_h) + 1
        if display_rows > term_rows - 1:
            display_rows = term_rows - 1
            display_cols = int(display_rows * cell_h / (aspect * cell_w))
        kitty_display(image_to_png(img), cols=display_cols, rows=display_rows)
        sys.stdout.write("\n")

    sys.stdout.flush()
    for img in images:
        img.close()


def png_pages(png_pattern: Path) -> list[Path]:
    return sorted(Path(p) for p in globmod.glob(str(png_pattern).replace("{p}", "*")))


def compile_and_display(typ_path: Path, png_pattern: Path) -> None:
    result = subprocess.run(
        [TYPST_BIN, "compile", "--format", "png", str(typ_path), str(png_pattern)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        sys.stdout.write(
            f"\033[2J\033[H\033[31mCompilation error:\033[0m\n{result.stderr}"
        )
        sys.stdout.flush()
        return
    display_pages(png_pages(png_pattern))


class TypstHandler(FileSystemEventHandler):
    def __init__(self, typ_path: Path, png_pattern: Path) -> None:
        self.typ_path = typ_path
        self.png_pattern = png_pattern
        self._last = 0.0

    def on_modified(self, event: FileSystemEvent) -> None:
        if Path(str(event.src_path)).resolve() != self.typ_path:
            return
        now = time.monotonic()
        if now - self._last < 0.2:
            return
        self._last = now
        compile_and_display(self.typ_path, self.png_pattern)


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def main(file: Path) -> None:
    typ_path = file.resolve()
    with tempfile.TemporaryDirectory(prefix="typst-watch-") as tmpdir:
        png_pattern = Path(tmpdir) / f"{typ_path.stem}.{{p}}.png"
        click.echo(f"Watching {typ_path.name} ...")
        compile_and_display(typ_path, png_pattern)

        observer = Observer()
        observer.schedule(TypstHandler(typ_path, png_pattern), str(typ_path.parent))
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
