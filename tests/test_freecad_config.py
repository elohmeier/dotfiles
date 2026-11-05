import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_toolbar_startup_with_separate_exec_namespaces(monkeypatch):
    import sys

    parameters = Mock()
    parameters.GetGroups.return_value = []
    gui = Mock()
    gui.Command.findCustomCommand.return_value = ""
    gui.Command.createCustomCommand.return_value = "Std_Macro_test"
    monkeypatch.setitem(
        sys.modules,
        "FreeCAD",
        SimpleNamespace(
            getUserAppDataDir=lambda: "/tmp/freecad/", ParamGet=lambda _: parameters
        ),
    )
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui)
    startup = (
        Path(__file__).resolve().parents[1]
        / "home/Library/Application Support/FreeCAD/v1-1/Mod/PrusaSlicerBridge/InitGui.py"
    )
    # FreeCAD executes InitGui.py inside a function, with distinct globals/locals.
    exec(compile(startup.read_text(), str(startup), "exec"), {}, {})
    gui.Command.createCustomCommand.assert_called_once()
    parameters.GetGroup.return_value.SetString.assert_any_call(
        "Std_Macro_test", "FreeCAD"
    )


def test_mcp_settings_preserve_local_credentials_and_are_idempotent(tmp_path):
    chezmoi = shutil.which("chezmoi")
    if chezmoi is None:
        pytest.skip("chezmoi is required")
    source = tmp_path / "source"
    source.mkdir()
    modifier = (
        Path(__file__).resolve().parents[1]
        / "home/Library/Application Support/FreeCAD/v1-1/modify_freecad_mcp_settings.json"
    )
    shutil.copyfile(modifier, source / modifier.name)
    destination = tmp_path / "destination"
    destination.mkdir()
    target = destination / "freecad_mcp_settings.json"
    target.write_text(
        json.dumps({"auth_token": "local-only-test-token", "unmanaged": "preserved"})
    )
    config = tmp_path / "chezmoi.toml"
    config.write_text("")
    command = [
        chezmoi,
        "--skip-secrets",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--config",
        str(config),
        "--persistent-state",
        str(tmp_path / "state.boltdb"),
        "apply",
        "--force",
        str(target),
    ]
    subprocess.run(command, check=True, capture_output=True)
    first = target.read_bytes()
    assert json.loads(first) == {
        "auth_token": "local-only-test-token",
        "unmanaged": "preserved",
        "remote_enabled": True,
        "allowed_ips": "127.0.0.1",
        "auto_start_rpc": False,
    }
    subprocess.run(command, check=True, capture_output=True)
    assert target.read_bytes() == first
