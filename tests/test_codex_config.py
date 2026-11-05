import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


def render_modifier(tmp_path: Path, platform: str = "linux") -> str:
    if shutil.which("chezmoi") is None:
        pytest.skip("chezmoi is required")
    source = Path(__file__).resolve().parents[1] / "home"
    config = tmp_path / "chezmoi.toml"
    config.write_text("")
    return subprocess.check_output(
        [
            "chezmoi",
            "--skip-secrets",
            "--source",
            str(source),
            "--config",
            str(config),
            "--override-data",
            json.dumps(
                {
                    "chezmoi": {
                        "os": platform,
                        "homeDir": str(tmp_path),
                        "workingTree": str(tmp_path / "dotfiles"),
                    },
                    "theme": "cyberdream",
                }
            ),
            "execute-template",
        ],
        input=(source / "dot_codex/modify_private_config.toml.tmpl").read_text(),
        text=True,
    )


def test_modifier_preserves_quoted_strings_and_is_idempotent(tmp_path):
    modifier = render_modifier(tmp_path)
    values = {
        "NODE_REPL_TRUSTED_SERVICES": json.dumps(
            {"browser": "/plugins/browser-service.mjs", "sky": "@oai/sky/service"}
        ),
        'quoted "key"': "Don't replace apostrophes",
        "controls": "first\nsecond\t\r\b\f\x00\x1f",
        "path": r"C:\Users\test\plugins",
        "unicode": "café ☃ 🚀",
    }
    current = "notify = []\n" + "\n".join(
        f"{json.dumps(key, ensure_ascii=False)} = {json.dumps(value, ensure_ascii=False)}"
        for key, value in values.items()
    )
    current += '\n[mcp_servers.other]\ncommand = "existing-server"\n'

    def run(text):
        return subprocess.check_output(
            [sys.executable, "-c", modifier], input=text, text=True
        )

    rendered = run(current)
    parsed = tomllib.loads(rendered)
    assert all(parsed[key] == value for key, value in values.items())
    assert "notify" not in parsed
    assert parsed["tui"]["theme"] == "cyberdream"
    assert parsed["projects"][str(tmp_path / "repos")]["trust_level"] == "trusted"
    assert parsed["mcp_servers"]["other"] == {"command": "existing-server"}
    assert run(rendered) == rendered


@pytest.mark.parametrize(
    ("platform", "installed"), [("linux", True), ("darwin", False), ("darwin", True)]
)
def test_freecad_mcp_requires_macos_and_installed_components(
    tmp_path, platform, installed
):
    uvx = shutil.which("uvx")
    if uvx is None:
        pytest.skip("uvx is required")
    freecadcmd = tmp_path / "Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd"
    if installed:
        freecadcmd.parent.mkdir(parents=True)
        freecadcmd.touch()
    modifier = render_modifier(tmp_path, platform)
    result = subprocess.check_output(
        [sys.executable, "-c", modifier], input="", text=True
    )
    config = tomllib.loads(result)
    if platform == "darwin" and installed:
        assert config["mcp_servers"]["freecad"] == {
            "command": uvx,
            "args": [
                "freecad-mcp@0.1.28",
                "--host",
                "127.0.0.1",
                "--freecadcmd",
                str(freecadcmd),
            ],
        }
    else:
        assert "freecad" not in config.get("mcp_servers", {})
