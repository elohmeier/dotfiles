import json
import os
import re
import shutil
import subprocess
import sys
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
    for name in (
        "fish nvim bat fzf vivid uv mise rbenv starship zoxide atuin tmux "
        "claude codex brew apk lbu tic"
    ).split():
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

    def run(platform, theme):
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
            json.dumps(
                {
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
                }
            ),
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
                input=contents,
                capture_output=True,
                text=True,
            )
            assert checked.returncode == 0, f"{name}: {checked.stderr}"
        if "<<'FISH'\n" in contents:
            body = contents.split("<<'FISH'\n", 1)[1].split("\nFISH", 1)[0]
            checked = subprocess.run(
                [tools["fish"], "--no-config", "-n"],
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
