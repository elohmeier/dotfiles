import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    device = tmp_path / "tpmrm0"
    device.touch(mode=0o600)
    rules = tmp_path / "rules.d"
    calls = tmp_path / "calls"
    calls.touch()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "PATH": str(bin_dir) + os.pathsep + os.defpath,
        "CALLS": str(calls),
        "DEVICE": str(device),
    }
    for name, body in {
        "id": 'case "$1" in -u) echo 1000;; -un) echo tester;; esac',
        "run0": 'echo run0 >>"$CALLS"\n[ "${DENY_AUTH:-0}" = 0 ] || exit 1\nexec "$@"',
        "udevadm": (
            'echo "udevadm $*" >>"$CALLS"\n'
            '[ "${FAIL_UDEV:-0}" = 0 ] || exit 1\n'
            '[ "$1" != trigger ] || chmod 600 "$DEVICE"'
        ),
        "systemctl": ('echo "systemctl $*" >>"$CALLS"\n[ "${FAIL_UNITS:-0}" = 0 ]'),
        "ssh-tpm-agent": "exit 0",
        "ssh-tpm-keygen": (
            'echo "keygen $*" >>"$CALLS"\n'
            'if [ "$1" = --print-pubkey ]; then echo public-key; else\n'
            'printf sealed-key >"$2.tpm"\n'
            'echo public-key >"$2.pub"\nfi'
        ),
    }.items():
        binary = bin_dir / name
        binary.write_text("#!/bin/sh\n" + body + "\n")
        binary.chmod(0o755)

    def run(script, **overrides):
        source = (ROOT / "scripts" / script).read_text()
        source = source.replace("/dev/tpmrm0", str(device)).replace(
            "/etc/udev/rules.d", str(rules)
        )
        script_path = tmp_path / script
        script_path.write_text(source)
        return subprocess.run(
            ["bash" if script.endswith("ssh.sh") else "sh", str(script_path)],
            input="n\n",
            env={**env, **overrides},
            text=True,
            capture_output=True,
        )

    return run, device, rules, calls, tmp_path


def test_udev_grants_invoking_uid_access_in_one_authorization(setup):
    run, device, rules, calls, _ = setup
    device.chmod(0)
    result = run("setup-tpm-udev.sh")
    assert result.returncode == 0, result.stderr
    assert (rules / "99-tpm.rules").read_text() == (
        'KERNEL=="tpmrm0", OWNER="1000", MODE="0600"\n'
    )
    assert calls.read_text().splitlines() == [
        "run0",
        "udevadm control --reload-rules",
        f"udevadm trigger --action=change --settle {device}",
    ]
    assert "no logout" in result.stdout


@pytest.mark.parametrize("failure", ("DENY_AUTH", "FAIL_UDEV"))
def test_udev_failures_stop_without_reporting_success(setup, failure):
    run, device, _, calls, _ = setup
    device.chmod(0)
    result = run("setup-tpm-udev.sh", **{failure: "1"})
    assert result.returncode == 1
    assert "setup failed" in result.stderr
    assert "polkit.service" in result.stderr
    assert "TPM access is ready" not in result.stdout
    assert "udevadm trigger" not in calls.read_text()


def test_udev_skips_authorization_when_access_is_ready(setup):
    run, _, rules, calls, _ = setup
    result = run("setup-tpm-udev.sh")
    assert result.returncode == 0
    assert not rules.exists()
    assert calls.read_text() == ""


@pytest.mark.parametrize("script", ("setup-tpm-udev.sh", "setup-tpm-ssh.sh"))
def test_missing_tpm_explains_firmware_setup(setup, script):
    run, device, _, calls, _ = setup
    device.unlink()
    result = run(script)
    assert result.returncode == 1
    assert "firmware" in result.stderr
    assert calls.read_text() == ""


def test_ssh_permission_failure_explains_repair_before_creating_keys(setup):
    run, device, _, calls, directory = setup
    device.chmod(0o400)
    result = run("setup-tpm-ssh.sh")
    assert result.returncode == 1
    assert "djust setup-tpm-udev" in result.stderr
    assert not (directory / ".ssh").exists()
    assert calls.read_text() == ""


@pytest.mark.parametrize("tool", ("ssh-tpm-agent", "ssh-tpm-keygen"))
def test_ssh_missing_tools_explains_installation(setup, tool):
    run, _, _, calls, directory = setup
    (directory / "bin" / tool).unlink()
    result = run("setup-tpm-ssh.sh")
    assert result.returncode == 1
    assert "brew install elohmeier/tap/ssh-tpm-agent; chezmoi apply" in result.stderr
    assert calls.read_text() == ""


def test_ssh_requires_units_before_creating_keys(setup):
    run, _, _, calls, directory = setup
    result = run("setup-tpm-ssh.sh", FAIL_UNITS="1")
    assert result.returncode == 1
    assert "chezmoi apply" in result.stderr
    assert not (directory / ".ssh").exists()
    assert "keygen" not in calls.read_text()


def test_ssh_creates_key_starts_agent_and_reuses_key_on_retry(setup):
    run, _, _, calls, directory = setup
    for _ in range(2):
        result = run("setup-tpm-ssh.sh")
        assert result.returncode == 0, result.stderr
    assert (directory / ".ssh/id_ecdsa.tpm").read_text() == "sealed-key"
    assert (directory / ".ssh/id_ecdsa.tpm").stat().st_mode & 0o777 == 0o600
    assert calls.read_text().count("keygen -f") == 1
    assert "systemctl --user enable --now ssh-tpm-agent.socket" in calls.read_text()
    assert "systemctl --user restart ssh-tpm-agent.service" in calls.read_text()
    assert "Reusing" in result.stdout


@pytest.mark.parametrize("existing", ("id_ecdsa", "id_ecdsa.pub"))
def test_ssh_preserves_existing_software_key(setup, existing):
    run, _, _, calls, directory = setup
    ssh = directory / ".ssh"
    ssh.mkdir()
    key = ssh / existing
    key.write_text("existing-key")
    result = run("setup-tpm-ssh.sh")
    assert result.returncode == 1
    assert "Move it aside" in result.stderr
    assert key.read_text() == "existing-key"
    assert "keygen" not in calls.read_text()


def test_ssh_restores_missing_public_key_without_replacing_tpm_key(setup):
    run, _, _, calls, directory = setup
    ssh = directory / ".ssh"
    ssh.mkdir()
    (ssh / "id_ecdsa.tpm").write_text("existing-key")
    result = run("setup-tpm-ssh.sh")
    assert result.returncode == 0, result.stderr
    assert (ssh / "id_ecdsa.tpm").read_text() == "existing-key"
    assert (ssh / "id_ecdsa.pub").read_text() == "public-key\n"
    assert "keygen -f" not in calls.read_text()


@pytest.mark.parametrize("platform", ("linux", "darwin"))
def test_tpm_recipes_are_available_on_linux_without_installed_tools(tmp_path, platform):
    chezmoi, just = shutil.which("chezmoi"), shutil.which("just")
    if not chezmoi or not just:
        pytest.skip("chezmoi and just are required for recipe validation")
    config = tmp_path / "chezmoi.toml"
    config.write_text('[data]\nforgejoURL = ""\nwoodpeckerURL = ""\n')
    result = subprocess.run(
        [
            chezmoi,
            "--config",
            str(config),
            "--source",
            str(ROOT / "home"),
            "--working-tree",
            str(ROOT),
            "--destination",
            str(tmp_path),
            "--persistent-state",
            str(tmp_path / "state.boltdb"),
            "--cache",
            str(tmp_path / "cache"),
            "--override-data",
            json.dumps({"chezmoi": {"os": platform}}),
            "execute-template",
            "--file",
            str(ROOT / "home/dot_config/just/dotfiles.just.tmpl"),
        ],
        env={**os.environ, "PATH": os.defpath},
        text=True,
        capture_output=True,
        check=True,
    )
    justfile = tmp_path / "dotfiles.just"
    justfile.write_text(result.stdout)
    listed = subprocess.run(
        [just, "--justfile", str(justfile), "--summary"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split()
    for recipe in ("setup-tpm-ssh", "setup-tpm-udev"):
        assert (recipe in listed) == (platform == "linux")
