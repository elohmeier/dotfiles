"""Host-only policy storage and browser approval bridge for Pi containers."""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

import click
import tomlkit


def project_root() -> Path | None:
    if "PI_EGRESS_PROJECT_ROOT" in os.environ:
        value = os.environ["PI_EGRESS_PROJECT_ROOT"]
        return Path(value).resolve() if value else None
    if os.environ.get("PI_EGRESS_DIR"):
        return None  # Explicit standalone contexts (including integration tests).
    for path in (Path.cwd(), *Path.cwd().parents):
        if (path / "mise.toml").is_file() or (path / ".git").exists():
            return path.resolve()
    return None


@dataclass
class Context:
    root: Path | None
    global_dir: Path
    state: Path

    @classmethod
    def current(cls) -> "Context":
        root = project_root()
        global_dir = Path(
            os.environ.get("PI_EGRESS_GLOBAL_DIR")
            or os.environ.get("PI_EGRESS_DIR")
            or Path.home() / ".local/state/pi-egress"
        ).resolve()
        state = global_dir / "global"
        if root:
            key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
            state = global_dir / "projects" / key
        state = Path(os.environ.get("PI_EGRESS_DIR", state)).resolve()
        return cls(root, global_dir, state)

    def init(self) -> None:
        for path in (self.global_dir, self.state):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.chmod(0o700)
        for name in ("pending", "decisions", "save"):
            (self.state / name).mkdir(exist_ok=True, mode=0o700)

    @contextmanager
    def lock(self):
        self.init()
        with (self.global_dir / ".rules.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def destination(self, scope: str, kind: str) -> Path:
        if scope == "project":
            if not self.root:
                raise click.ClickException("Project scope requires a project directory")
            return self.root / "mise.toml"
        return self.global_dir / f"rules.{kind}"


def atomic_write(path: Path, content: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        if path.exists():
            os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "w") as file:
            file.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def patterns(value: str) -> list[str]:
    return sorted(set(re.split(r"[\s,]+", value.strip().lower())) - {""})


def read_rules(path: Path) -> list[str]:
    if not path.exists():
        return []
    return patterns(
        "\n".join(
            line
            for line in path.read_text().splitlines()
            if not line.lstrip().startswith("#")
        )
    )


def update_rules(values: list[str], pattern: str, remove: bool) -> str:
    updated = set(values)
    if remove:
        updated.discard(pattern)
    else:
        updated.add(pattern)
    return "\n".join(sorted(updated)) + ("\n" if updated else "")


def edit_rule(ctx: Context, scope: str, kind: str, pattern: str, remove=False) -> None:
    """Caller holds the global lock; activate only the explicitly approved delta."""
    if not pattern or re.search(r"[\s,/#?]", pattern):
        raise click.ClickException("Expected a host pattern, optionally with a port")
    pattern = pattern.lower()
    target = ctx.destination(scope, kind)
    if scope == "project":
        if target.is_symlink():
            raise click.ClickException("Refusing to edit a symlinked mise.toml")
        document = (
            tomlkit.parse(target.read_text()) if target.exists() else tomlkit.document()
        )
        if "env" not in document:
            document["env"] = tomlkit.table()
        env = document["env"]
        key = f"PI_EGRESS_{kind.upper()}"
        value = env.get(key, "")
        if not isinstance(value, str) or "{{" in value:
            raise click.ClickException(f"{key} must be a literal string to edit it")
        updated = update_rules(patterns(value), pattern, remove).strip()
        env[key] = (
            tomlkit.string("\n" + updated + "\n", multiline=True)
            if "\n" in updated
            else updated
        )
        atomic_write(target, tomlkit.dumps(document))
        snapshot = ctx.state / f"project.{kind}"
        atomic_write(snapshot, update_rules(read_rules(snapshot), pattern, remove))
    else:
        content = update_rules(read_rules(target), pattern, remove)
        atomic_write(target, content)
        # Each proxy gets a snapshot, never a mount exposing other projects.
        for state in {
            ctx.state,
            ctx.global_dir / "global",
            *(ctx.global_dir / "projects").glob("*"),
        }:
            if state != ctx.global_dir and state.is_dir():
                atomic_write(state / f"rules.{kind}", content)
    click.echo(f"{'Removed' if remove else 'Saved'} {pattern}: {scope} → {target}")


@click.group()
def main() -> None:
    """Internal host helper; use mise run pi:egress for the public interface."""


@main.command("context")
def context_command() -> None:
    ctx = Context.current()
    values = {
        "PI_EGRESS_PROJECT_ROOT": str(ctx.root or ""),
        "PI_EGRESS_GLOBAL_DIR": str(ctx.global_dir),
        "PI_EGRESS_DIR": str(ctx.state),
        "PI_EGRESS_NAME": os.environ.get(
            "PI_EGRESS_NAME", f"pi-egress-{ctx.state.name}" if ctx.root else "pi-egress"
        ),
        "PI_EGRESS_WEB_PORT": os.environ.get(
            "PI_EGRESS_WEB_PORT", "0" if ctx.root else "8081"
        ),
        "PI_EGRESS_SUBNET": os.environ.get(
            "PI_EGRESS_SUBNET", "" if ctx.root else "10.223.0.0/24"
        ),
        "PI_EGRESS_PROXY_IP": os.environ.get(
            "PI_EGRESS_PROXY_IP", "" if ctx.root else "10.223.0.2"
        ),
    }
    for key, value in values.items():
        click.echo(f"export {key}={shlex.quote(value)}")


@main.command()
def snapshot() -> None:
    """Explicit launch/reload boundary: snapshot the host's resolved environment."""
    ctx = Context.current()
    with ctx.lock():
        for kind in ("allow", "deny"):
            atomic_write(
                ctx.state / f"project.{kind}",
                "\n".join(patterns(os.environ.get(f"PI_EGRESS_{kind.upper()}", "")))
                + "\n",
            )
            global_file = ctx.global_dir / f"rules.{kind}"
            if not global_file.exists():
                atomic_write(global_file, "")
            if ctx.state != ctx.global_dir:
                atomic_write(ctx.state / f"rules.{kind}", global_file.read_text())
        atomic_write(ctx.state / "project", str(ctx.root or "global") + "\n")


@main.command()
@click.argument("kind", type=click.Choice(["allow", "deny"]))
@click.argument("pattern")
@click.option("--scope", type=click.Choice(["global", "project"]), default="global")
@click.option("--remove", is_flag=True)
def rule(kind: str, pattern: str, scope: str, remove: bool) -> None:
    ctx = Context.current()
    with ctx.lock():
        edit_rule(ctx, scope, kind, pattern, remove)


@main.command("start-bridge")
@click.argument("runtime")
@click.argument("proxy")
@click.option("--scope", type=click.Choice(["global", "project"]), default="global")
def start_bridge(runtime: str, proxy: str, scope: str) -> None:
    ctx = Context.current()
    with ctx.lock():
        ctx.destination(scope, "allow")
        atomic_write(ctx.state / "save-scope", scope + "\n")
    subprocess.Popen(
        [sys.executable, "-m", "scripts.pi_egress_control", "bridge", runtime, proxy],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@main.command()
@click.argument("runtime")
@click.argument("proxy")
def bridge(runtime: str, proxy: str) -> None:
    """Only fixed pending-request IDs cross this boundary, never paths or code."""
    ctx = Context.current()
    ctx.init()
    with (ctx.state / ".bridge.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        while True:
            running = subprocess.run(
                [runtime, "inspect", "-f", "{{.State.Running}}", proxy],
                capture_output=True,
                text=True,
            )
            if running.returncode or running.stdout.strip() != "true":
                return
            atomic_write(ctx.state / "bridge-ready", str(time.time()))
            for _ in range(4):
                process_saves(ctx)
                time.sleep(0.25)


def process_saves(ctx: Context) -> None:
    with ctx.lock():
        for queued in (ctx.state / "save").iterdir():
            if not re.fullmatch(r"[0-9a-f]{16}", queued.name):
                continue
            request = ctx.state / "pending" / queued.name
            decision = ctx.state / "decisions" / queued.name
            try:
                payload = json.loads(queued.read_text())
                scope, kind = payload["scope"], payload["kind"]
                if scope not in ("project", "global") or kind not in ("allow", "deny"):
                    raise ValueError("Invalid save request")
                if not request.exists() or decision.exists():
                    continue
                timeout = next(
                    (
                        int(line.split("=", 1)[1])
                        for line in (ctx.state / "config").read_text().splitlines()
                        if line.startswith("timeout=")
                    ),
                    60,
                )
                if time.time() >= request.stat().st_mtime + timeout:
                    continue
                edit_rule(ctx, scope, kind, request.read_text().strip())
                atomic_write(decision, kind)
                (ctx.state / "save-error").unlink(missing_ok=True)
            except (OSError, ValueError, KeyError, click.ClickException) as error:
                atomic_write(ctx.state / "save-error", str(error))
                atomic_write(decision, "deny")
            finally:
                queued.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
