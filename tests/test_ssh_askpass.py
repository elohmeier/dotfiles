import fcntl
import os
import pty
import select
import shutil
import struct
import subprocess
import termios
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tpm_scripts(tmp_path):
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
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.defpath,
        "XDG_RUNTIME_DIR": str(runtime),
        "DISPLAY": ":test",
        "WAYLAND_DISPLAY": "",
        "TMUX": "/test/tmux,123,0",
        "TMUX_PANE": "%3",
    }
    for name, body in {
        "logger": 'printf "%s\\n" "$*" >>"$XDG_RUNTIME_DIR/journal"',
        "tmux": (
            'if [ "$1" = list-clients ]; then\n'
            '  [ "${DETACHED:-0}" = 1 ] || printf "/dev/pts/test\\n"\n'
            "  exit 0\nfi\n"
            'printf "%s\\n" "$@" >"$XDG_RUNTIME_DIR/popup"\n'
            'while [ "$1" != --terminal ]; do script=$1; shift; done\n'
            'printf "%s" "$POPUP_INPUT" | "$script" "$@"'
        ),
        "ssh-add": (
            'printf "%s\\n" "$SSH_AUTH_SOCK" "$@" >"$XDG_RUNTIME_DIR/signing"\n'
            '[ "${UNLOCKED:-0}" = 1 ] && exit 0\n'
            'answer=$("$ASKPASS" "Unlock test key: ") || exit 1\n'
            '[ "$answer" = "$EXPECTED_PIN" ]'
        ),
    }.items():
        script = bin_dir / name
        script.write_text("#!/bin/sh\n" + body + "\n")
        script.chmod(0o755)

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

    script = bin_dir / "ssh-tpm-askpass"
    script.write_text(render("dot_local/bin/executable_ssh-tpm-askpass.tmpl"))
    script.chmod(0o755)
    unlock = bin_dir / "ssh-tpm-unlock"
    unlock.write_text(render("dot_local/bin/executable_ssh-tpm-unlock.tmpl"))
    unlock.chmod(0o755)
    env["ASKPASS"] = str(script)
    service = render("dot_config/systemd/user/ssh-tpm-agent.service.tmpl")
    assert "Environment=SSH_ASKPASS=%h/.local/bin/ssh-tpm-askpass\n" in service
    assert "Environment=SSH_ASKPASS_REQUIRE=force\n" in service
    return env, script, unlock, runtime


@pytest.fixture
def askpass(tpm_scripts, tmp_path):
    env, script, _, _ = tpm_scripts

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
            timeout=5,
            check=False,
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
        (b"D partial\nOK\n", "", 7, b"", False, "GETPIN"),
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


@pytest.mark.parametrize("stale_target", [False, True])
def test_headless_askpass_fails_without_a_live_unlock(tpm_scripts, stale_target):
    env, script, _, runtime = tpm_scripts
    if stale_target:
        request = runtime / "ssh-tpm-unlock"
        request.mkdir(mode=0o700)
        (request / "target").write_text("/wrong/socket\n/wrong/client\n")
        (request / "lock").touch()
    result = subprocess.run(
        [str(script), "Unlock test key: "],
        env={**env, "DISPLAY": "", "WAYLAND_DISPLAY": ""},
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert "ssh-tpm-unlock" in (runtime / "journal").read_text()
    assert not (runtime / "popup").exists()


@pytest.mark.parametrize(
    ("hint", "answer", "success", "pin"),
    [
        ("", " synthetic p%in\\word \n", True, " synthetic p%in\\word "),
        ("", "", False, ""),
        ("confirm", "y\n", True, ""),
        ("confirm", "n\n", False, ""),
        ("none", "\n", True, ""),
    ],
)
def test_unlock_routes_to_its_tmux_client_and_cleans_up(
    tpm_scripts, hint, answer, success, pin
):
    env, _, unlock, runtime = tpm_scripts
    key = str(runtime / "chosen key.pub")
    result = subprocess.run(
        [str(unlock), key],
        env={
            **env,
            "DISPLAY": "",
            "SSH_AUTH_SOCK": "/forwarded/agent.sock",
            "SSH_ASKPASS_PROMPT": hint,
            "POPUP_INPUT": answer,
            "EXPECTED_PIN": pin,
        },
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert (result.returncode == 0) == success, result.stderr
    assert "key is ready" in result.stdout.decode() if success else not result.stdout
    if pin:
        assert pin.encode() not in result.stdout + result.stderr
    assert (runtime / "signing").read_text().splitlines() == [
        str(runtime / "ssh-tpm-agent.sock"),
        "-T",
        key,
    ]
    popup = (runtime / "popup").read_text().splitlines()
    assert popup[:6] == [
        "-S",
        "/test/tmux",
        "display-popup",
        "-c",
        "/dev/pts/test",
        "-E",
    ]
    assert not (runtime / "ssh-tpm-unlock/target").exists()
    assert not list(runtime.glob("ssh-tpm-askpass.*"))


def test_usable_key_needs_no_popup(tpm_scripts):
    env, _, unlock, runtime = tpm_scripts
    result = subprocess.run(
        [str(unlock)],
        env={**env, "UNLOCKED": "1"},
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not (runtime / "popup").exists()
    assert not (runtime / "ssh-tpm-unlock/target").exists()


@pytest.mark.parametrize("detached", [False, True])
def test_unlock_requires_an_attached_tmux_session(tpm_scripts, detached):
    env, _, unlock, runtime = tpm_scripts
    result = subprocess.run(
        [str(unlock)],
        env={**env, **({"DETACHED": "1"} if detached else {"TMUX": ""})},
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert not (runtime / "signing").exists()


def test_concurrent_unlock_preserves_the_active_target(tpm_scripts):
    env, _, unlock, runtime = tpm_scripts
    request = runtime / "ssh-tpm-unlock"
    request.mkdir(mode=0o700)
    target = request / "target"
    target.write_text("active target\n")
    with (request / "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(
            [str(unlock)], env=env, capture_output=True, timeout=5, check=False
        )
    assert result.returncode == 1
    assert b"already running" in result.stderr
    assert target.read_text() == "active target\n"
    assert not (runtime / "signing").exists()


def test_missing_popup_client_fails_promptly(tpm_scripts):
    env, _, unlock, runtime = tpm_scripts
    tmux = unlock.parent / "tmux"
    tmux.write_text(
        '#!/bin/sh\n[ "$1" = list-clients ] || exit 1\nprintf "/dev/pts/gone\\n"\n'
    )
    result = subprocess.run(
        [str(unlock)], env=env, capture_output=True, timeout=5, check=False
    )
    assert result.returncode == 1
    assert not (runtime / "ssh-tpm-unlock/target").exists()
    assert not list(runtime.glob("ssh-tpm-askpass.*"))


@pytest.mark.parametrize("cancel", [False, True])
def test_real_tmux_popup_hides_input_and_handles_ctrl_c(tpm_scripts, cancel):
    env, askpass, unlock, runtime = tpm_scripts
    tmux = shutil.which("tmux")
    if not tmux:
        pytest.skip("tmux is required for popup validation")
    for script in (askpass, unlock):
        script.write_text(script.read_text().replace(str(unlock.parent / "tmux"), tmux))
    runner = runtime / "runner"
    runner.write_text(
        '#!/bin/sh\nssh-tpm-unlock >"$XDG_RUNTIME_DIR/result" 2>&1\n'
        'printf "%s" "$?" >"$XDG_RUNTIME_DIR/status"\nsleep 10\n'
    )
    socket = runtime / "tmux.sock"
    pin = b"synthetic-popup-pin"
    env = {**env, "DISPLAY": "", "TERM": "xterm-256color", "EXPECTED_PIN": pin.decode()}
    pid, terminal = pty.fork()
    if pid == 0:
        os.execvpe(
            tmux,
            [
                tmux,
                "-S",
                str(socket),
                "-f",
                "/dev/null",
                "new-session",
                "sh",
                str(runner),
            ],
            env,
        )
    screen = b""
    sent = False
    try:
        fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not (runtime / "status").exists():
            if select.select([terminal], [], [], 0.05)[0]:
                screen += os.read(terminal, 65536)
            if not sent and b"Unlock test key:" in screen:
                os.write(terminal, b"\x03" if cancel else pin + b"\r")
                sent = True
        assert sent, "The real tmux popup did not display its prompt"
        assert (runtime / "status").read_text() == ("1" if cancel else "0")
        assert pin not in screen
        assert pin not in (runtime / "result").read_bytes()
        assert not (runtime / "ssh-tpm-unlock/target").exists()
        assert not list(runtime.glob("ssh-tpm-askpass.*"))
    finally:
        subprocess.run(
            [tmux, "-S", str(socket), "kill-server"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        os.close(terminal)
        os.waitpid(pid, 0)
