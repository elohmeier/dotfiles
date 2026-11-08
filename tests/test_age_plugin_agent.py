import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(platform.system() != "Darwin", reason="LaunchAgent is macOS-only")
@pytest.mark.parametrize("help_text", ["age-plugin-se agent [--socket PATH]", "keygen"])
def test_launch_agent_needs_agent_capable_plugin(tmp_path, help_text):
    chezmoi = shutil.which("chezmoi")
    if not chezmoi:
        pytest.skip("chezmoi is required for template validation")
    plugin = tmp_path / "bin" / "age-plugin-se"
    plugin.parent.mkdir()
    plugin.write_text(f"#!/bin/sh\necho '  {help_text}'\n")
    plugin.chmod(0o755)
    (tmp_path / "chezmoi.toml").write_text("")
    plist = subprocess.run(
        [
            chezmoi,
            "--config",
            str(tmp_path / "chezmoi.toml"),
            "--source",
            str(ROOT / "home"),
            "--persistent-state",
            str(tmp_path / "state.boltdb"),
            "execute-template",
            "--file",
            str(
                ROOT
                / "home/Library/private_LaunchAgents/de.enno.age-plugin-se-agent.plist.tmpl"
            ),
        ],
        env={**os.environ, "PATH": f"{plugin.parent}{os.pathsep}{os.defpath}"},
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    if "agent" in help_text:
        assert f"<string>{plugin}</string>\n    <string>agent</string>" in plist
    else:
        assert not plist.strip()
