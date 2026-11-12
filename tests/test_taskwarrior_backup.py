import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_backup_history_snapshot_and_restore(tmp_path):
    tools = {
        name: shutil.which(name) for name in ("chezmoi", "task", "git", "jq", "sqlite3")
    }
    if not all(tools.values()):
        pytest.skip("chezmoi, Taskwarrior 3, Git, jq, and sqlite3 are required")
    task = tools["task"]
    git = tools["git"]
    assert task and git
    if not subprocess.check_output([task, "--version"], text=True).startswith("3."):
        pytest.skip("Taskwarrior 3 is required")

    data = tmp_path / "data"
    data.mkdir()
    config = tmp_path / "taskrc"
    config.write_text("confirmation=off\nhooks=off\nrecurrence=off\n")
    backup = tmp_path / "backups"
    env = {
        **os.environ,
        "TASKRC": str(config),
        "TASKDATA": str(data),
        "TASKWARRIOR_BACKUP_DIR": str(backup),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Backup test",
        "GIT_AUTHOR_EMAIL": "backup@example.invalid",
        "GIT_COMMITTER_NAME": "Backup test",
        "GIT_COMMITTER_EMAIL": "backup@example.invalid",
    }

    def run(*args, **kwargs):
        return subprocess.run(
            args, env=env, check=True, capture_output=True, text=True, **kwargs
        )

    chezmoi_config = tmp_path / "chezmoi.toml"
    chezmoi_config.touch()
    template = ROOT / "home/dot_local/bin/executable_taskwarrior-backup.tmpl"
    script = tmp_path / "taskwarrior-backup"
    script.write_text(
        run(
            tools["chezmoi"],
            "--config",
            str(chezmoi_config),
            "execute-template",
            input=template.read_text(),
        ).stdout
    )
    script.chmod(0o700)
    run(task, "rc.verbose=nothing", "add", "First task", "+backup-test")
    run(task, "rc.verbose=nothing", "add", "Completed task")
    run(task, "rc.verbose=nothing", "2", "done")

    # Hold committed data in the WAL to exercise the online SQLite backup.
    with sqlite3.connect(data / "taskchampion.sqlite3") as connection:
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE backup_test (value TEXT)")
        connection.execute("INSERT INTO backup_test VALUES ('committed WAL data')")
        connection.commit()
        source_files = [
            data / "taskchampion.sqlite3",
            data / "taskchampion.sqlite3-wal",
        ]
        source_contents = [path.read_bytes() for path in source_files]
        run(str(script))
        assert [path.read_bytes() for path in source_files] == source_contents
        first_export = (backup / "tasks.json").read_text()
        tasks = json.loads(first_export)
        assert {task["status"] for task in tasks} == {"pending", "completed"}
        assert all("id" not in task and "urgency" not in task for task in tasks)
        assert [task["uuid"] for task in tasks] == sorted(
            task["uuid"] for task in tasks
        )
        snapshots = list((backup / "snapshots").glob("*.sqlite3"))
        assert len(snapshots) == 1
        with sqlite3.connect(snapshots[0]) as snapshot:
            assert snapshot.execute("PRAGMA quick_check").fetchone() == ("ok",)
            assert snapshot.execute("SELECT value FROM backup_test").fetchone() == (
                "committed WAL data",
            )
        assert list(connection.execute("SELECT value FROM backup_test")) == [
            ("committed WAL data",)
        ]

        run(str(script))
        assert (backup / "tasks.json").read_text() == first_export
        assert (
            run(git, "-C", str(backup), "rev-list", "--count", "HEAD").stdout.strip()
            == "1"
        )

        # Concurrent uncommitted writes must not affect the backup.
        connection.execute("BEGIN EXCLUSIVE")
        connection.execute("UPDATE backup_test SET value='uncommitted'")
        run(str(script))
        connection.rollback()
        assert (backup / "tasks.json").read_text() == first_export

    run(task, "rc.verbose=nothing", "add", "Another task")
    with (backup / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run(str(script))
        assert (backup / "tasks.json").read_text() == first_export
    run(str(script))
    assert (
        run(git, "-C", str(backup), "rev-list", "--count", "HEAD").stdout.strip() == "2"
    )
    assert run(git, "-C", str(backup), "status", "--porcelain").stdout == ""
    assert len(list((backup / "snapshots").glob("*.sqlite3"))) == 1

    # A failure leaves the previous successful backup intact.
    last_export = (backup / "tasks.json").read_text()
    env["TASKDATA"] = str(tmp_path / "missing")
    assert subprocess.run([str(script)], env=env, capture_output=True).returncode != 0
    assert (backup / "tasks.json").read_text() == last_export

    restore = tmp_path / "restore"
    restore.mkdir()
    env["TASKDATA"] = str(restore)
    run(task, "rc.verbose=nothing", "import", str(backup / "tasks.json"))
    restored = json.loads(
        run(task, "rc.verbose=nothing", "rc.json.array=on", "export").stdout
    )
    for restored_task in restored:
        restored_task.pop("id", None)
        restored_task.pop("urgency", None)
    assert sorted(restored, key=lambda task: task["uuid"]) == json.loads(
        (backup / "tasks.json").read_text()
    )
