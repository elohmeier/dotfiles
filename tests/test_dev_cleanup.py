import fcntl
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tools(tmp_path):
    if sys.platform != "linux":
        pytest.skip("Linux cache maintenance")
    home = tmp_path / "home"
    home.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "commands"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
        "CLEANUP_LOG": str(log),
        "XDG_CACHE_HOME": str(home / ".cache"),
    }

    def stub(name, contents):
        script = binaries / name
        script.write_text("#!/bin/sh\n" + contents + "\n")
        script.chmod(0o755)

    return home, log, env, stub


def render_cleanup(tools, tmp_path):
    home, _log, env, stub = tools
    chezmoi = shutil.which("chezmoi")
    if not chezmoi:
        pytest.skip("chezmoi required")
    for name in ("cargo-sweep", "docker", "podman"):
        stub(name, f'printf \'{name} %s\\n\' "$*" >> "$CLEANUP_LOG"')
    project = home / "repos/host/owner/project"
    (project / "target/debug").mkdir(parents=True)
    (project / "Cargo.toml").write_text("")
    (project / "target/debug/.cargo-lock").touch()
    stub("cargo", f"printf '%s\\n' '{{\"target_directory\":\"{project}/target\"}}'")
    (home / ".cache").mkdir()
    source = tmp_path / "source"
    source.mkdir()
    template = ROOT / "home/dot_local/bin/executable_dev-cleanup.tmpl"
    rendered = subprocess.run(
        [
            chezmoi,
            "--source",
            str(source),
            "--config",
            str(tmp_path / "chezmoi.toml"),
            "--skip-secrets",
            "execute-template",
        ],
        input=template.read_text(),
        text=True,
        env=env,
        check=True,
        capture_output=True,
    ).stdout
    script = tmp_path / "dev-cleanup"
    script.write_text(rendered)
    return script, project


def test_cleanup_uses_local_stores_and_preserves_volumes(tools, tmp_path):
    _home, log, env, _stub = tools
    script, _project = render_cleanup(tools, tmp_path)
    subprocess.run(["bash", str(script), "--dry-run"], env=env, check=True)
    assert "prune" not in log.read_text()
    log.unlink()
    subprocess.run(["bash", str(script)], env=env, check=True)
    commands = log.read_text().splitlines()
    prunes = [line for line in commands if "prune" in line]
    assert len(prunes) == 4
    assert all("--host unix:///var/run/docker.sock" in x for x in prunes[:3])
    assert prunes[3].startswith("podman --remote=false system prune")
    assert "--max-used-space 40GB" in prunes[0]
    assert all("--filter until=168h" in x for x in prunes[1:])
    assert all("--volumes" not in x and "volume prune" not in x for x in prunes)
    assert any("sweep --maxsize 40GB" in x for x in commands)


def test_cleanup_skips_a_busy_cargo_target(tools, tmp_path):
    _home, log, env, _stub = tools
    script, project = render_cleanup(tools, tmp_path)
    with (project / "target/debug/.cargo-lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        subprocess.run(["bash", str(script)], env=env, check=True)
    commands = log.read_text()
    assert "cargo-sweep" not in commands
    assert "docker --host unix:///var/run/docker.sock builder prune" in commands


def migration_tools(tools):
    home, log, env, stub = tools
    stub(
        "getent", f"printf 'test:x:{os.getuid()}:{os.getgid()}::%s:/bin/sh\\n' '{home}'"
    )
    stub("findmnt", "echo btrfs")
    stub("systemctl", 'test "${USER_MANAGER_ACTIVE:-0}" = 1')
    stub(
        "btrfs", 'mkdir "$3"; touch "$3/.test-subvolume"; echo create >> "$CLEANUP_LOG"'
    )
    stat = shutil.which("stat")
    cp = shutil.which("cp")
    assert stat and cp
    stub(
        "stat",
        'if [ "$2" = %i ] && [ -f "$3/.test-subvolume" ]; then echo 256; '
        f'else exec "{stat}" "$@"; fi',
    )
    stub("cp", f'shift 2; exec "{cp}" -a "$@"')
    return home, log, env


def test_cache_migration_preserves_contents_and_is_idempotent(tools):
    home, log, env = migration_tools(tools)
    cache = home / ".cache"
    cache.mkdir(mode=0o700)
    (cache / "data").write_text("keep this")
    (home / "source").write_text("source survives")
    (cache / "link").symlink_to(home / "source")
    os.link(cache / "data", cache / "hardlink")
    command = [
        "bash",
        str(ROOT / "scripts/btrfs-cache-subvolumes.sh"),
        str(os.getuid()),
    ]
    subprocess.run(command, env=env, check=True)
    assert (cache / "data").read_text() == "keep this"
    assert (cache / "link").is_symlink()
    assert (home / "source").read_text() == "source survives"
    assert (cache / "data").stat().st_ino == (cache / "hardlink").stat().st_ino
    assert cache.stat().st_mode & 0o777 == 0o700
    assert not (home / ".cache.chezmoi-subvolume").exists()
    creates = log.read_text()
    subprocess.run(command, env=env, check=True)
    assert log.read_text() == creates


def test_cache_migration_refuses_a_running_user_manager(tools):
    home, log, env = migration_tools(tools)
    cache = home / ".cache"
    cache.mkdir()
    (cache / "data").write_text("untouched")
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/btrfs-cache-subvolumes.sh"), str(os.getuid())],
        check=False,
        env={**env, "USER_MANAGER_ACTIVE": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "before user@" in result.stderr
    assert (cache / "data").read_text() == "untouched"
    assert not log.exists()


def test_failed_cache_copy_keeps_original_and_refuses_retry(tools):
    home, log, env = migration_tools(tools)
    cache = home / ".cache"
    cache.mkdir()
    (cache / "data").write_text("original")
    stub = tools[3]
    stub("cp", "exit 1")
    command = [
        "bash",
        str(ROOT / "scripts/btrfs-cache-subvolumes.sh"),
        str(os.getuid()),
    ]
    assert subprocess.run(command, env=env, check=False).returncode == 1
    assert (cache / "data").read_text() == "original"
    created = log.read_text()
    result = subprocess.run(
        command, env=env, check=False, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "needs inspection" in result.stderr
    assert log.read_text() == created


def test_cache_migration_leaves_symlinked_external_storage_alone(tools, tmp_path):
    home, _log, env = migration_tools(tools)
    external = tmp_path / "external"
    (external / "registry").mkdir(parents=True)
    (external / "registry/data").write_text("external data")
    (home / ".cargo").symlink_to(external, target_is_directory=True)
    subprocess.run(
        ["bash", str(ROOT / "scripts/btrfs-cache-subvolumes.sh"), str(os.getuid())],
        env=env,
        check=True,
    )
    assert (external / "registry/data").read_text() == "external data"
    assert not (external / "registry/.test-subvolume").exists()
    assert not (external / "git").exists()
