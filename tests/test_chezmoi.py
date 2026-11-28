import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
THEMES = ("tokyonight_day", "tokyonight_night", "cyberdream_light", "cyberdream")


@pytest.fixture
def render(tmp_path):
    tools = {}
    for name in ("chezmoi", "fish", "bash", "zsh", "jq"):
        executable = shutil.which(name)
        if executable is None:
            pytest.skip(f"{name} is required for dotfiles validation")
        tools[name] = executable

    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in [
        "fish",
        "nvim",
        "bat",
        "fzf",
        "vivid",
        "uv",
        "mise",
        "rbenv",
        "starship",
        "zoxide",
        "atuin",
        "tmux",
        "claude",
        "codex",
        "agy",
        "brew",
        "apk",
        "lbu",
        "tic",
        "task",
        "git",
        "sqlite3",
        "lockf",
        "flock",
    ]:
        binary = bin_dir / name
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
    for name, output in {
        "stat": "ext4",
        "sha256sum": "test-ca-hash",
        "npm": "12.0.0",
    }.items():
        binary = bin_dir / name
        binary.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n")
        binary.chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    (bin_dir / "jq").symlink_to(tools["jq"])
    env = {
        "HOME": str(home),
        "PATH": str(bin_dir) + os.pathsep + os.defpath,
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local/share"),
    }

    def run(platform, theme, extra_data=None):
        override_data = {
            "chezmoi": {
                "os": "linux" if platform == "wsl" else platform,
                "hostname": "test",
                "homeDir": str(home),
                "kernel": {
                    "osrelease": "microsoft-standard-WSL2"
                    if platform == "wsl"
                    else platform
                },
            },
            "isWSL": platform == "wsl",
            "theme": theme,
            **(extra_data or {}),
        }
        args = [
            tools["chezmoi"],
            "--no-tty",
            "--skip-secrets",
            "--source",
            str(ROOT / "home"),
            "--working-tree",
            str(ROOT),
            "--destination",
            str(home),
            "--config",
            str(tmp_path / "chezmoi.toml"),
            "--persistent-state",
            str(tmp_path / "state.boltdb"),
            "--cache",
            str(tmp_path / "cache"),
            "--override-data",
            json.dumps(override_data),
        ]
        subprocess.run(
            [*args, "init", "--data=false", "--promptDefaults"],
            env=env,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            [*args, "dump", "--format=json"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout), tools

    return run


@pytest.mark.parametrize("platform", ("darwin", "linux", "wsl"))
@pytest.mark.parametrize("theme", THEMES)
def test_rendered_configuration(render, platform, theme):
    entries, tools = render(platform, theme)
    assert ".config/fish/config.fish" in entries
    assert ".local/bin/taskwarrior-backup" in entries
    assert (".local/bin/ocr" in entries) == (platform == "darwin")
    assert ("Library/LaunchAgents/de.enno.taskwarrior-backup.plist" in entries) == (
        platform == "darwin"
    )
    assert (".config/systemd/user/taskwarrior-backup.timer" in entries) == (
        platform != "darwin"
    )
    assert ("Library/Application Support/k9s" in entries) == (platform == "darwin")
    assert any(".chezmoiscripts/wsl/" in name for name in entries) == (
        platform == "wsl"
    )
    assert any(".chezmoiscripts/darwin/" in name for name in entries) == (
        platform == "darwin"
    )
    assert any(".chezmoiscripts/linux/" in name for name in entries) == (
        platform != "darwin"
    )

    for name, entry in entries.items():
        if entry["type"] not in ("file", "script"):
            continue
        contents = entry.get("contents", "")
        suffix = Path(name).suffix
        if suffix == ".json":
            json.loads(contents)
        elif suffix == ".plist":
            plistlib.loads(contents.encode())
        elif suffix == ".toml":
            tomllib.loads(contents)
        elif suffix in (".yaml", ".yml"):
            yaml.safe_load(contents)

        shell = None
        if suffix == ".fish":
            shell = "fish"
        elif name in (".bashrc", ".zshrc"):
            shell = name[1:-2]
        elif match := re.match(r"^#![^\n]*\b(bash|sh|zsh)\s*(?:\n|$)", contents):
            shell = match[1]
        if shell:
            checked = subprocess.run(
                [tools.get(shell, shell), "-n"],
                check=False,
                input=contents,
                capture_output=True,
                text=True,
            )
            assert checked.returncode == 0, f"{name}: {checked.stderr}"
        if "<<'FISH'\n" in contents:
            body = contents.split("<<'FISH'\n", 1)[1].split("\nFISH", 1)[0]
            checked = subprocess.run(
                [tools["fish"], "--no-config", "-n"],
                check=False,
                input=body,
                capture_output=True,
                text=True,
            )
            assert checked.returncode == 0, f"{name}: {checked.stderr}"


def test_bootstrap_detects_tools_installed_by_package_hook(tmp_path):
    executable = shutil.which("chezmoi")
    if executable is None:
        pytest.skip("chezmoi is required for bootstrap validation")
    home = tmp_path / "home"
    source = tmp_path / "source"
    hooks = source / ".chezmoiscripts"
    hooks.mkdir(parents=True)
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (source / "tool.tmpl").write_text('{{ if lookPath "new-tool" }}installed{{ end }}')
    (hooks / "run_onchange_before_install-packages.sh.tmpl").write_text(
        f"#!/bin/sh\nprintf '#!/bin/sh\\n' > '{bin_dir}/new-tool'\n"
        f"chmod +x '{bin_dir}/new-tool'\n"
    )
    config = tmp_path / "chezmoi.toml"
    config.write_text("")
    wrapper = bin_dir / "chezmoi"
    wrapper.write_text(
        f"#!/bin/sh\nexec '{executable}' --source '{source}' "
        f"--destination '{home}' --config '{config}' "
        f"--persistent-state '{tmp_path}/state.boltdb' \"$@\"\n"
    )
    wrapper.chmod(0o755)
    subprocess.run(
        ["sh", str(ROOT / "scripts/bootstrap.sh")],
        env={"HOME": str(home), "PATH": str(bin_dir) + os.pathsep + os.defpath},
        check=True,
        capture_output=True,
    )
    assert (home / "tool").read_text() == "installed"


def test_antigravity_pushover_plugin_and_notifier(render, tmp_path):
    entries_off, _ = render("linux", "tokyonight_day")
    assert ".gemini/config/plugins/pushover/plugin.json" not in entries_off
    assert ".gemini/config/plugins/pushover/hooks.json" not in entries_off

    entries, tools = render(
        "linux",
        "tokyonight_day",
        extra_data={"pushoverUserKey": "user-key", "pushoverApiToken": "api-token"},
    )
    plugin = json.loads(
        entries[".gemini/config/plugins/pushover/plugin.json"]["contents"]
    )
    hooks = json.loads(
        entries[".gemini/config/plugins/pushover/hooks.json"]["contents"]
    )
    assert plugin["name"] == "pushover"
    assert hooks["pushover"]["Stop"][0]["command"].endswith(
        "/.local/bin/agent-pushover-notify Antigravity"
    )
    assert hooks["pushover"]["PreToolUse"][0]["matcher"] == "ask_question"

    script_src = entries[".local/bin/agent-pushover-notify"]["contents"]
    subprocess.run(
        [tools.get("sh", "sh"), "-n"], input=script_src, text=True, check=True
    )

    encrypted_entries, _ = render(
        "linux",
        "tokyonight_day",
        extra_data={
            "pushoverUserKey": "user-key",
            "pushoverApiToken": "api-token",
            "pushoverEncryptionKey": "0" * 64,
        },
    )
    subprocess.run(
        [tools.get("sh", "sh"), "-n"],
        input=encrypted_entries[".local/bin/agent-pushover-notify"]["contents"],
        text=True,
        check=True,
    )

    log = tmp_path / "curl.log"
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{log}'\n")
    fake_curl.chmod(0o755)
    script = tmp_path / "agent-pushover-notify"
    script.write_text(re.sub(r"\S+/curl\b", str(fake_curl), script_src))
    script.chmod(0o755)

    project = tmp_path / "demo-repo"
    project.mkdir()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps(step)
            for step in (
                {"type": "USER_INPUT", "content": "old prompt"},
                {"type": "PLANNER_RESPONSE", "content": "stale reply"},
                {"type": "USER_INPUT", "content": "new prompt"},
                {
                    "type": "PLANNER_RESPONSE",
                    "content": "**All** [tests](https://example.com) passed",
                },
            )
        )
        + "\n"
    )

    def wait_for_log():
        for _ in range(50):
            if log.exists() and log.stat().st_size > 0:
                return log.read_text()
            time.sleep(0.05)
        raise AssertionError("curl was not invoked")

    # 1. Stop (normal) reads latest PLANNER_RESPONSE after last USER_INPUT
    res = subprocess.run(
        [str(script), "Antigravity"],
        input=json.dumps(
            {
                "hookEventName": "Stop",
                "terminationReason": "NO_TOOL_CALL",
                "cwd": str(project),
                "transcriptPath": str(transcript),
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(res.stdout) == {"decision": "stop"}
    sent = wait_for_log()
    assert "title=demo-repo · Antigravity" in sent
    assert "message=All tests passed\n—" in sent
    assert "sound=classical" in sent

    # 2. Stop (USER_CANCELED) suppresses Pushover
    log.unlink()
    res = subprocess.run(
        [str(script), "Antigravity"],
        input=json.dumps(
            {
                "hookEventName": "Stop",
                "terminationReason": "USER_CANCELED",
                "cwd": str(project),
                "transcriptPath": str(transcript),
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(res.stdout) == {"decision": "stop"}
    time.sleep(0.2)
    assert not log.exists()

    # 3. Stop (ERROR) surfaces error instead of stale reply
    res = subprocess.run(
        [str(script), "Antigravity"],
        input=json.dumps(
            {
                "hookEventName": "Stop",
                "terminationReason": "ERROR",
                "error": "rate limit exceeded",
                "cwd": str(project),
                "transcriptPath": str(transcript),
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(res.stdout) == {"decision": "stop"}
    sent = wait_for_log()
    assert "message=rate limit exceeded\n—" in sent

    # 4. PreToolUse (ask_question) allows tool and notifies with questions
    log.unlink()
    res = subprocess.run(
        [str(script), "Antigravity"],
        input=json.dumps(
            {
                "hookEventName": "PreToolUse",
                "cwd": str(project),
                "toolCall": {
                    "name": "ask_question",
                    "args": {
                        "questions": [
                            {"question": "Deploy to prod?"},
                            {"question": "Run migrations?"},
                        ]
                    },
                },
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(res.stdout) == {"decision": "allow"}
    sent = wait_for_log()
    assert "title=demo-repo · Antigravity needs input" in sent
    assert "message=Deploy to prod?\nRun migrations?\n—" in sent
