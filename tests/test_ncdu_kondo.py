import io
import json
import os
import shutil
import subprocess
import threading
from collections import Counter
from pathlib import Path

import pytest
from click.testing import CliRunner

from scripts import ncdu_kondo as kondo


def touch(root: Path, name: str, contents: str = "fixture") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    return path


def test_discovery_requires_markers_and_finds_nested_projects(tmp_path):
    for name in (
        "app/package.json",
        "app/node_modules/dependency/package.json",
        "app/node_modules/dependency/node_modules/file",
        "app/packages/nested/Cargo.toml",
        "app/packages/nested/target/file",
        "scala/build.sbt",
        "scala/project/target/file",
        "unrelated/build/source.c",
        "unrelated/vendor/source.php",
        "unrelated/node_modules/file",
        "python/src/__pycache__/module.pyc",
        "python/.venv/pyvenv.cfg",
        "unrelated/venv/source.py",
        ".git/example/package.json",
        ".git/example/node_modules/file",
        "archived/package.json",
        "archived/node_modules/file",
    ):
        touch(tmp_path, name)
    (tmp_path / "linked-project").symlink_to(tmp_path / "app", target_is_directory=True)
    (tmp_path / "app/.next").symlink_to(
        tmp_path / "unrelated", target_is_directory=True
    )
    found = kondo.discover(tmp_path, kondo.VCS | {"archived"})
    assert {str(path.relative_to(tmp_path)) for path in found} == {
        "app/node_modules",
        "app/packages/nested/target",
        "scala/project/target",
        "python/src/__pycache__",
        "python/.venv",
    }


def test_discovery_does_not_enumerate_cache_contents(tmp_path, monkeypatch):
    touch(tmp_path, "package.json")
    touch(tmp_path, "node_modules/contents")
    scandir = os.scandir
    visited = []

    def record(path):
        visited.append(path)
        return scandir(path)

    monkeypatch.setattr(kondo.os, "scandir", record)
    assert kondo.discover(tmp_path, kondo.VCS) == [tmp_path / "node_modules"]
    assert visited == [tmp_path]


@pytest.mark.parametrize("jobs", [1, 4])
def test_export_preserves_metadata_links_and_real_paths(tmp_path, jobs):
    source = touch(tmp_path, "source.txt")
    cache = tmp_path / 'project "☃"/node_modules'
    original = touch(cache, "original", "a" * 10_000)
    os.link(original, cache / "hardlink")
    (cache / "symlink").symlink_to(source)
    (cache / "loop").symlink_to(cache, target_is_directory=True)
    (cache / "empty").mkdir()
    output = io.StringIO()
    kondo.export(tmp_path, [cache], output, jobs)
    data = json.loads(output.getvalue())
    assert data[:2] == [1, 2]
    tree = data[3]
    assert tree[0] == {"name": str(tmp_path)}
    assert len(tree) == 2  # source file is absent
    assert tree[1][0] == {"name": cache.parent.name}
    entries = {
        (entry[0] if isinstance(entry, list) else entry)["name"]: entry
        for entry in tree[1][1][1:]
    }
    info = original.stat()
    assert entries["original"]["asize"] == info.st_size
    assert entries["original"]["dsize"] == info.st_blocks * 512
    assert entries["original"]["mtime"] == int(info.st_mtime)
    assert entries["original"]["ino"] == entries["hardlink"]["ino"]
    assert entries["original"]["nlink"] == 2
    assert entries["symlink"]["notreg"] is True
    assert entries["loop"]["notreg"] is True
    assert len(entries["empty"]) == 1


def test_export_does_not_require_ncdu(tmp_path, monkeypatch):
    monkeypatch.setattr(kondo.shutil, "which", lambda _: None)
    touch(tmp_path, "package.json")
    touch(tmp_path, "node_modules/file")
    destination = tmp_path / "export.json"
    result = CliRunner().invoke(
        kondo.cli, [str(tmp_path), "--export", str(destination)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(destination.read_text())[3][1][0]["name"] == "node_modules"
    assert (tmp_path / "node_modules/file").exists()


def test_launcher_enforces_builtin_deletion_and_cleans_temporary_export(
    tmp_path, monkeypatch
):
    touch(tmp_path, "package.json")
    touch(tmp_path, "node_modules/file")
    monkeypatch.setattr(kondo.shutil, "which", lambda _: "/usr/bin/ncdu")
    scans = []

    def run(args, **kwargs):
        scan = Path(args[args.index("-f") + 1])
        scans.append(scan)
        assert json.loads(scan.read_text())[3][0]["name"] == str(tmp_path.resolve())
        assert args == [
            "ncdu",
            "--ignore-config",
            "-e",
            "-f",
            str(scan),
            "--enable-delete",
            "--confirm-delete",
            "--disable-refresh",
            "--disable-shell",
        ]
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(kondo.subprocess, "run", run)
    result = CliRunner().invoke(kondo.cli, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(scans) == 1
    assert not scans[0].exists()


def test_scan_failure_does_not_launch_ncdu_or_replace_export(tmp_path, monkeypatch):
    touch(tmp_path, "package.json")
    touch(tmp_path, "node_modules/file")
    destination = touch(tmp_path, "export.json", "previous export")

    def fail(*args):
        raise PermissionError("fixture permission denied")

    monkeypatch.setattr(kondo, "write_artifact", fail)
    result = CliRunner().invoke(
        kondo.cli, [str(tmp_path), "--export", str(destination)]
    )
    assert result.exit_code == 1
    assert "fixture permission denied" in result.output
    assert destination.read_text() == "previous export"


def test_parallel_matches_serial_and_visits_each_directory_once(tmp_path, monkeypatch):
    for index in range(40):
        touch(tmp_path, f"node_modules/package-{index}/nested/file")
    os.link(
        tmp_path / "node_modules/package-0/nested/file",
        tmp_path / "node_modules/package-39/hardlink",
    )
    (tmp_path / "node_modules/link").symlink_to(tmp_path, target_is_directory=True)
    touch(tmp_path, 'node_modules/line\n"☃"')
    if kondo.sys.platform == "linux":
        raw_path = os.fsencode(tmp_path / "node_modules") + b"/invalid-\xff"
        with open(raw_path, "wb") as raw:
            raw.write(b"fixture")
    cache = tmp_path / "node_modules"
    scans = Counter()
    lock = threading.Lock()
    original = os.scandir

    def record(path):
        if str(path).startswith(str(cache)):
            with lock:
                scans[str(path)] += 1
        return original(path)

    monkeypatch.setattr(kondo.os, "scandir", record)
    monkeypatch.setattr(kondo.time, "time", lambda: 123456)
    serial = io.StringIO()
    kondo.export(tmp_path, [cache], serial, jobs=1)
    serial_scans = scans.copy()
    scans.clear()
    parallel = io.StringIO()
    kondo.export(tmp_path, [cache], parallel, jobs=4)
    assert parallel.getvalue() == serial.getvalue()
    assert scans == serial_scans
    assert set(scans.values()) == {1}


def test_parallel_workers_overlap_and_clean_up_spools(tmp_path, monkeypatch):
    for index in range(30):
        touch(tmp_path, f"node_modules/package-{index}/file")
    original = kondo.spool
    barrier = threading.Barrier(2, timeout=5)
    lock = threading.Lock()
    workers = set()
    destinations = []

    def record(parts, destination):
        with lock:
            first_two = len(destinations) < 2
            destinations.append(destination)
            workers.add(threading.get_ident())
        if first_two:
            barrier.wait()
        return original(parts, destination)

    monkeypatch.setattr(kondo, "spool", record)
    output = io.StringIO()
    kondo.export(tmp_path, [tmp_path / "node_modules"], output, jobs=2)
    assert len(workers) == 2
    assert all(not path.parent.exists() for path in destinations)
    assert len(json.loads(output.getvalue())[3][1]) == 31


def test_worker_failure_cleans_spools(tmp_path, monkeypatch):
    for index in range(30):
        touch(tmp_path, f"node_modules/package-{index}/file")
    original = kondo.spool
    destinations = []

    def fail(parts, destination):
        destinations.append(destination)
        original(parts, destination)
        raise PermissionError("worker failed")

    monkeypatch.setattr(kondo, "spool", fail)
    with pytest.raises(PermissionError, match="worker failed"):
        kondo.export(tmp_path, [tmp_path / "node_modules"], io.StringIO(), jobs=2)
    assert destinations
    assert all(not path.parent.exists() for path in destinations)


def test_main_bootstraps_isolated_free_threaded_runtime(monkeypatch):
    monkeypatch.setattr(kondo.sys, "_is_gil_enabled", lambda: True, raising=False)
    monkeypatch.setattr(kondo.sys, "version", "3.13.5")
    monkeypatch.setattr(
        kondo.sys, "argv", ["ncdu-kondo", "some directory", "--jobs", "2"]
    )
    calls = []

    def execute(executable, args):
        calls.append((executable, args))
        raise SystemExit(0)

    monkeypatch.setattr(kondo.os, "execvp", execute)
    with pytest.raises(SystemExit):
        kondo.main()
    assert calls == [
        (
            "uv",
            [
                "uv",
                "run",
                "--python",
                "3.14t",
                "--script",
                kondo.__file__,
                "some directory",
                "--jobs",
                "2",
            ],
        )
    ]


def test_timings_use_readonly_import(tmp_path, monkeypatch):
    touch(tmp_path, "package.json")
    touch(tmp_path, "node_modules/file")
    monkeypatch.setattr(kondo.shutil, "which", lambda _: "/usr/bin/ncdu")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert "--quit-after-scan" in args
        assert "--enable-delete" not in args
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(kondo.subprocess, "run", run)
    result = CliRunner().invoke(
        kondo.cli,
        [
            str(tmp_path),
            "--export",
            str(tmp_path / "scan.json"),
            "--jobs",
            "1",
            "--timings",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert "Discovery:" in result.output
    assert "Scan/export:" in result.output
    assert "ncdu import (extra pass):" in result.output


def test_free_threaded_runtime_does_not_reexec(monkeypatch):
    monkeypatch.setattr(kondo.sys, "_is_gil_enabled", lambda: False, raising=False)
    calls = []
    monkeypatch.setattr(kondo, "cli", lambda **kwargs: calls.append(kwargs))
    kondo.main()
    assert calls == [{"prog_name": "ncdu-kondo"}]


def test_explicitly_enabled_gil_cannot_cause_reexec_loop(monkeypatch):
    monkeypatch.setattr(kondo.sys, "_is_gil_enabled", lambda: True, raising=False)
    monkeypatch.setattr(kondo.sys, "version", "3.14.7 free-threading build")
    with pytest.raises(SystemExit, match="GIL is enabled"):
        kondo.main()


@pytest.mark.skipif(shutil.which("ncdu") is None, reason="ncdu is not installed")
def test_real_ncdu_import(tmp_path):
    root = tmp_path / "projects"
    touch(root, "node/package.json")
    touch(root, "node/node_modules/dependency/file", "contents")
    touch(root, "node/source.js")
    scan = tmp_path / "scan.json"
    with scan.open("w") as output:
        kondo.export(root, kondo.discover(root, kondo.VCS), output)
    imported = json.loads(
        subprocess.check_output(
            ["ncdu", "--ignore-config", "-e", "-f", str(scan), "-o", "-"],
            stderr=subprocess.DEVNULL,
        )
    )[3]
    assert imported[0]["name"] == str(root)
    project = imported[1]
    assert len(project) == 2
    assert project[0]["name"] == "node"
    assert project[1][0]["name"] == "node_modules"
    assert project[1][1][1]["asize"] == len("contents")
