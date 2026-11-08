import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def askpass(tmp_path):
    chezmoi = shutil.which("chezmoi")
    if not chezmoi:
        pytest.skip("chezmoi is required for template validation")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pinentry = bin_dir / "pinentry-gnome3"
    pinentry.write_text(
        '#!/bin/sh\ncat >"$REQUEST"\ncat "$RESPONSE"\nexit "$PINENTRY_EXIT"\n'
    )
    pinentry.chmod(0o755)
    config = tmp_path / "chezmoi.toml"
    config.write_text("")
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.defpath}

    def render(source):
        return subprocess.run(
            [
                chezmoi,
                "--config",
                str(config),
                "--source",
                str(ROOT / "home"),
                "--persistent-state",
                str(tmp_path / "state.boltdb"),
                "execute-template",
                "--file",
                str(ROOT / "home" / source),
            ],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout

    script = tmp_path / "askpass"
    script.write_text(render("dot_local/bin/executable_ssh-tpm-askpass.tmpl"))
    service = render("dot_config/systemd/user/ssh-tpm-agent.service.tmpl")
    assert "Environment=SSH_ASKPASS=%h/.local/bin/ssh-tpm-askpass\n" in service

    def run(response, hint, pinentry_exit=0):
        response_file = tmp_path / "response"
        response_file.write_bytes(response)
        request = tmp_path / "request"
        result = subprocess.run(
            ["bash", str(script), "Key 100%:\r\nBYE\\\nGETPIN"],
            env={
                **env,
                "REQUEST": str(request),
                "RESPONSE": str(response_file),
                "PINENTRY_EXIT": str(pinentry_exit),
                "SSH_ASKPASS_PROMPT": hint,
            },
            capture_output=True,
        )
        return result, request.read_text().splitlines()

    return run


@pytest.mark.parametrize(
    ("response", "hint", "pinentry_exit", "expected", "success", "command"),
    [
        (
            b"OK\nD  p%25ass\\word%0D%0A\nD end \nOK\n",
            "",
            0,
            b" p%ass\\word\r\nend ",
            True,
            "GETPIN",
        ),
        (b"OK\nD literal%250A\nOK\n", "", 0, b"literal%0A", True, "GETPIN"),
        (b"OK\nERR 83886179 Operation cancelled\n", "", 0, b"", False, "GETPIN"),
        (b"D partial\nERR 1 Failed\n", "", 0, b"", False, "GETPIN"),
        (b"", "", 7, b"", False, "GETPIN"),
        (b"OK\nOK\n", "confirm", 0, b"", True, "CONFIRM"),
        (b"ERR 1 Not confirmed\n", "confirm", 0, b"", False, "CONFIRM"),
        (b"OK\nOK\n", "none", 0, b"", True, "CONFIRM --one-button"),
    ],
)
def test_askpass_protocol(
    askpass, response, hint, pinentry_exit, expected, success, command
):
    result, request = askpass(response, hint, pinentry_exit)
    assert (result.returncode == 0) == success, result.stderr
    assert result.stdout == expected
    assert request == [
        "SETTITLE SSH key",
        "SETDESC Key 100%25:%0D%0ABYE%5C%0AGETPIN",
        command,
        "BYE",
    ]
