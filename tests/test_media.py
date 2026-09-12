import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from scripts import media


@pytest.mark.parametrize(
    "command,action", [("mount-media", "mount"), ("umount-media", "unmount")]
)
@pytest.mark.parametrize("mounted", [False, True])
def test_commands_select_the_card_and_handle_current_mount_state(
    command, action, mounted, monkeypatch
):
    def inventory(args, **_):
        assert args[0] == "/usr/bin/lsblk"
        assert "--tree" in args
        return json.dumps({"blockdevices": [disk("/dev/sda1")]})

    monkeypatch.setattr(media.subprocess, "check_output", inventory)
    monkeypatch.setattr(Path, "is_block_device", lambda _: True)
    monkeypatch.setattr(media.signal, "signal", lambda *_: None)
    monkeypatch.setattr(
        media, "mountpoint", lambda _: Path("/media/SD") if mounted else None
    )
    operation = MagicMock()
    monkeypatch.setattr(media, "udisks", operation)
    result = CliRunner().invoke(media.main, prog_name=command)
    assert result.exit_code == 0, result.output
    if (action == "mount") != mounted:
        operation.assert_called_once_with(action, "/dev/sda1")
    else:
        operation.assert_not_called()
        assert "already" in result.output


def test_ambiguous_card_never_mounts(monkeypatch):
    monkeypatch.setattr(
        media.subprocess,
        "check_output",
        lambda *_, **__: json.dumps({"blockdevices": [disk("/dev/sda1", "/dev/sda2")]}),
    )
    monkeypatch.setattr(media.signal, "signal", lambda *_: None)
    operation = MagicMock()
    monkeypatch.setattr(media, "udisks", operation)
    result = CliRunner().invoke(media.main, prog_name="mount-media")
    assert result.exit_code == 1
    assert "--device" in result.output
    operation.assert_not_called()


def test_explicit_device_resolves_symlinks(tmp_path, monkeypatch):
    device = tmp_path / "card"
    device.symlink_to("/dev/null")
    monkeypatch.setattr(
        media.subprocess,
        "check_output",
        lambda *_, **__: json.dumps({"blockdevices": [disk("/dev/null")]}),
    )
    monkeypatch.setattr(Path, "is_block_device", lambda _: True)
    monkeypatch.setattr(media.signal, "signal", lambda *_: None)
    monkeypatch.setattr(media, "mountpoint", lambda _: None)
    operation = MagicMock()
    monkeypatch.setattr(media, "udisks", operation)
    result = CliRunner().invoke(
        media.main, ["--device", str(device)], prog_name="mount-media"
    )
    assert result.exit_code == 0, result.output
    operation.assert_called_once_with("mount", "/dev/null")


@pytest.mark.parametrize(
    "command,action", [("mount-media", "mount"), ("umount-media", "unmount")]
)
@pytest.mark.parametrize("filesystem", ["iso9660", "udf"])
def test_optical_device_does_not_require_direct_read_access(
    command, action, filesystem, monkeypatch
):
    monkeypatch.setattr(
        media,
        "block_devices",
        lambda: [
            {"path": "/dev/null", "type": "rom", "rm": True, "fstype": filesystem}
        ],
    )
    monkeypatch.setattr(os, "access", lambda *_: False)
    monkeypatch.setattr(Path, "is_block_device", lambda _: True)
    monkeypatch.setattr(media.signal, "signal", lambda *_: None)
    monkeypatch.setattr(
        media,
        "mountpoint",
        lambda _: Path("/media/disc") if action == "unmount" else None,
    )
    operation = MagicMock()
    monkeypatch.setattr(media, "udisks", operation)
    result = CliRunner().invoke(
        media.main, ["--device", "/dev/null"], prog_name=command
    )
    assert result.exit_code == 0, result.output
    operation.assert_called_once_with(action, "/dev/null")


def disk(*partitions, removable=True):
    return {
        "path": "/dev/sda",
        "type": "disk",
        "rm": removable,
        "children": [
            {"path": name, "type": "part", "fstype": "vfat"} for name in partitions
        ],
    }


def test_card_or_exact_partition():
    inventory = [disk("/dev/sda1")]
    assert media.partition_for(inventory, "/dev/sda") == "/dev/sda1"
    assert media.partition_for(inventory, "/dev/sda1") == "/dev/sda1"
    inventory = [disk("/dev/sda1", "/dev/sda2")]
    assert media.partition_for(inventory, "/dev/sda2") == "/dev/sda2"
    with pytest.raises(ValueError, match="exactly one"):
        media.partition_for(inventory, "/dev/sda")


def test_internal_and_absent_disks_are_rejected():
    with pytest.raises(ValueError, match="removable"):
        media.partition_for([disk("/dev/sda1", removable=False)], "/dev/sda1")
    with pytest.raises(ValueError, match="no mountable filesystem.* /dev/sdb"):
        media.partition_for([disk("/dev/sda1")], "/dev/sdb")


@pytest.mark.parametrize("filesystem", ["vfat", "exfat", "ext4", "ntfs", "btrfs"])
@pytest.mark.parametrize("partitioned", [True, False])
def test_auto_selects_only_removable_filesystem(filesystem, partitioned):
    card = disk("/dev/sda1") if partitioned else disk()
    target = card["children"][0] if partitioned else card
    target["fstype"] = filesystem
    internal = disk("/dev/nvme0n1p1", removable=False)
    internal["path"] = "/dev/nvme0n1"
    unsupported = disk("/dev/sdb1")
    unsupported["path"] = "/dev/sdb"
    unsupported["children"][0]["fstype"] = "swap"
    assert media.partition_for([internal, unsupported, card]) == target["path"]


@pytest.mark.parametrize(
    "inventory", [[], [disk("/dev/sda1", removable=False)], [disk()]]
)
def test_auto_rejects_absent_or_unsuitable_cards(inventory):
    with pytest.raises(ValueError, match="no mountable filesystem"):
        media.partition_for(inventory)


@pytest.mark.parametrize("filesystem", ["iso9660", "udf"])
def test_optical_media_selection(filesystem):
    disc = {"path": "/dev/sr0", "type": "rom", "rm": True, "fstype": filesystem}
    assert media.partition_for([disc]) == "/dev/sr0"
    assert media.partition_for([disc], "/dev/sr0") == "/dev/sr0"
    with pytest.raises(ValueError, match="multiple.*--device"):
        media.partition_for([disk("/dev/sda1"), disc])
    disc["fstype"] = None
    with pytest.raises(ValueError, match="no mountable filesystem"):
        media.partition_for([disc], "/dev/sr0")


def test_usb_disk_without_removable_flag():
    usb = disk("/dev/sda1", removable=False)
    usb["hotplug"] = True
    usb["children"][0]["fstype"] = "ext4"
    assert media.partition_for([usb]) == "/dev/sda1"
    assert media.partition_for([usb], "/dev/sda") == "/dev/sda1"


@pytest.mark.parametrize(
    "filesystem",
    [None, "swap", "crypto_LUKS", "BitLocker", "LVM2_member", "linux_raid_member"],
)
def test_non_filesystem_media_is_rejected(filesystem):
    device = disk("/dev/sda1")
    device["children"][0]["fstype"] = filesystem
    with pytest.raises(ValueError, match="no mountable filesystem"):
        media.partition_for([device], "/dev/sda1")


@pytest.mark.parametrize("command", ["mount-media", "umount-media"])
@pytest.mark.parametrize(
    "words,incomplete,expected",
    [
        ("--", "--", ["--device", "--help"]),
        ("--device ", "", ["/dev/sda1", "/dev/sr0"]),
        ("--device /dev/sr", "/dev/sr", ["/dev/sr0"]),
    ],
)
def test_fish_completion(command, words, incomplete, expected, monkeypatch):
    monkeypatch.setattr(
        media,
        "block_devices",
        lambda: [
            disk("/dev/sda1"),
            disk("/dev/nvme0n1p1", removable=False),
            {"path": "/dev/sr0", "type": "rom", "rm": True, "fstype": "udf"},
            {"path": "/dev/sr1", "type": "rom", "rm": True, "fstype": None},
        ],
    )
    operation = MagicMock()
    monkeypatch.setattr(media, "udisks", operation)
    result = CliRunner().invoke(
        media.main,
        prog_name=command,
        env={
            f"_{command.upper().replace('-', '_')}_COMPLETE": "fish_complete",
            "COMP_WORDS": f"{command} {words}",
            "COMP_CWORD": incomplete,
        },
    )
    assert result.exit_code == 0, result.output
    assert [
        line.split(",", 1)[1].split("\t")[0] for line in result.output.splitlines()
    ] == expected
    operation.assert_not_called()


@pytest.mark.parametrize("separate_disks", [True, False])
def test_auto_requires_explicit_selection_for_multiple_destinations(separate_disks):
    if separate_disks:
        other = disk("/dev/sdb1")
        other["path"] = "/dev/sdb"
        inventory = [disk("/dev/sda1"), other]
        alternative = "/dev/sdb1"
    else:
        inventory = [disk("/dev/sda1", "/dev/sda2")]
        alternative = "/dev/sda2"
    with pytest.raises(ValueError, match="multiple.*--device") as error:
        media.partition_for(inventory)
    assert "/dev/sda1" in str(error.value)
    assert alternative in str(error.value)
    assert media.partition_for(inventory, alternative) == alternative


@pytest.mark.parametrize("interactive", [True, False])
def test_authentication_only_prompts_in_a_terminal(interactive, monkeypatch):
    commands = []
    monkeypatch.setattr(media, "polkit_authorized", lambda: True)
    monkeypatch.setattr(media.sys.stdin, "isatty", lambda: interactive)
    monkeypatch.setattr(
        media.subprocess, "run", lambda command, **_: commands.append(command)
    )
    monkeypatch.setattr(media, "run_authenticated", commands.append)
    media.udisks("mount", "/dev/sda1")
    assert ("--no-user-interaction" in commands[0]) is not interactive


@pytest.mark.parametrize("action,mounted", [("mount", False), ("unmount", True)])
def test_unauthorized_session_uses_docker_root_instead_of_prompting(
    action, mounted, monkeypatch
):
    commands = []
    monkeypatch.setattr(media, "polkit_authorized", lambda: False)
    monkeypatch.setattr(media, "docker_root", lambda: True)
    monkeypatch.setattr(media, "root_script", lambda *args: f"handle {args}")
    monkeypatch.setattr(
        media.subprocess, "run", lambda command, **_: commands.append(command)
    )
    monkeypatch.setattr(
        media,
        "run_authenticated",
        MagicMock(side_effect=AssertionError("must not open a password prompt")),
    )
    media.udisks(action, "/dev/sda1")
    assert commands == [
        [*media.DOCKER_ROOT, f"handle {(action, '/dev/sda1')}"],
    ]


def test_authorized_session_never_consults_docker(monkeypatch):
    monkeypatch.setattr(media, "polkit_authorized", lambda: True)
    monkeypatch.setattr(
        media,
        "docker_root",
        MagicMock(side_effect=AssertionError("docker must not be consulted")),
    )
    monkeypatch.setattr(media.sys.stdin, "isatty", lambda: True)
    executed = MagicMock()
    monkeypatch.setattr(media, "run_authenticated", executed)
    media.udisks("mount", "/dev/sda1")
    executed.assert_called_once()


@pytest.mark.parametrize(
    "filesystem,owned", [("vfat", True), ("iso9660", True), ("ext4", False)]
)
def test_root_mount_script_targets_run_media_with_owner_options(
    filesystem, owned, monkeypatch
):
    monkeypatch.setattr(
        media.subprocess,
        "check_output",
        lambda *_, **__: json.dumps(
            {
                "blockdevices": [
                    {"fstype": filesystem, "label": "SD CARD", "uuid": "AB-12"}
                ]
            }
        ),
    )
    monkeypatch.setattr(media.getpass, "getuser", lambda: "gordon")
    script = media.root_script("mount", "/dev/sda1")
    assert script.startswith("mkdir -p '/run/media/gordon/SD CARD' && mount -o nosuid")
    assert (f",uid={os.getuid()},gid={os.getgid()}" in script) is owned


def test_root_mount_script_falls_back_to_uuid(monkeypatch):
    monkeypatch.setattr(
        media.subprocess,
        "check_output",
        lambda *_, **__: json.dumps(
            {"blockdevices": [{"fstype": "exfat", "label": None, "uuid": "AB-12"}]}
        ),
    )
    monkeypatch.setattr(media.getpass, "getuser", lambda: "gordon")
    assert "/run/media/gordon/AB-12" in media.root_script("mount", "/dev/sda1")


def test_root_unmount_script_removes_the_mountpoint(monkeypatch):
    monkeypatch.setattr(media, "mountpoint", lambda _: Path("/run/media/gordon/SD"))
    assert media.root_script("unmount", "/dev/sda1") == (
        "umount /dev/sda1; rmdir /run/media/gordon/SD || :"
    )


def test_noninteractive_copy_never_starts_authentication_agent(monkeypatch):
    monkeypatch.setattr(media.sys.stdin, "isatty", lambda: False)
    start = MagicMock(
        side_effect=AssertionError("must not open an authentication prompt")
    )
    monkeypatch.setattr(media.subprocess, "Popen", start)
    with media.terminal_authentication(os.getpid()):
        pass
    start.assert_not_called()


def test_terminal_agent_is_ready_before_copy_and_cleaned_up_on_failure(monkeypatch):
    # A real child acknowledges registration by closing its inherited pipe,
    # then waits. No system polkit service or password prompt is used here.
    monkeypatch.setattr(media.sys.stdin, "isatty", lambda: True)
    popen = subprocess.Popen
    children = []

    def start(command, *, pass_fds):
        assert command[:3] == ["pkttyagent", "--process", str(os.getpid())]
        assert "--fallback" not in command
        child = popen(
            [
                sys.executable,
                "-c",
                "import os,signal,sys; os.close(int(sys.argv[1])); signal.pause()",
                str(pass_fds[0]),
            ],
            pass_fds=pass_fds,
        )
        children.append(child)
        return child

    monkeypatch.setattr(media.subprocess, "Popen", start)
    with pytest.raises(KeyboardInterrupt), media.terminal_authentication(os.getpid()):
        assert children[0].poll() is None
        raise KeyboardInterrupt
    assert children[0].returncode is not None


@pytest.mark.parametrize("exited", [True, False])
def test_agent_startup_failure_prevents_copy_and_cleans_up(exited, monkeypatch):
    monkeypatch.setattr(media.sys.stdin, "isatty", lambda: True)
    agent = MagicMock()
    agent.poll.return_value = 127 if exited else None
    monkeypatch.setattr(media.subprocess, "Popen", lambda *_, **__: agent)
    monkeypatch.setattr(
        media.select, "select", lambda *args: ([args[0][0]] if exited else [], [], [])
    )
    with (
        pytest.raises(OSError, match="could not start terminal authentication"),
        media.terminal_authentication(os.getpid()),
    ):
        pytest.fail("copy must not start without the requested terminal agent")
    agent.wait.assert_called_once_with(timeout=5)
    assert agent.terminate.called is not exited


def test_mount_timeout_is_reported(monkeypatch):
    monkeypatch.setattr(media, "polkit_authorized", lambda: True)
    monkeypatch.setattr(media.sys.stdin, "isatty", lambda: False)

    def stall(command, *, check, timeout):
        assert timeout == media.UDISKS_TIMEOUT
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(media.subprocess, "run", stall)
    with pytest.raises(OSError, match="mount timed out.*check mount state"):
        media.udisks("mount", "/dev/sda1")


def test_command_uses_the_exact_authenticated_pid_after_registration(
    tmp_path, monkeypatch
):
    result = tmp_path / "executed-pid"
    subjects = []

    @contextmanager
    def registered(subject_pid):
        assert subject_pid != os.getpid()
        assert not result.exists(), "command must wait for its terminal agent"
        subjects.append(subject_pid)
        yield

    monkeypatch.setattr(media, "terminal_authentication", registered)
    media.run_authenticated(
        [
            sys.executable,
            "-c",
            "import os,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))",
            str(result),
        ]
    )
    assert result.read_text() == str(subjects[0])


def test_failed_registration_stops_waiting_command(tmp_path, monkeypatch):
    result = tmp_path / "must-not-exist"
    children = []
    popen = subprocess.Popen

    def start(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    @contextmanager
    def failed(_):
        raise OSError("authentication agent unavailable")
        yield  # noqa: B027 -- make this a context manager which fails on entry

    monkeypatch.setattr(media.subprocess, "Popen", start)
    monkeypatch.setattr(media, "terminal_authentication", failed)
    with pytest.raises(OSError, match="authentication agent unavailable"):
        media.run_authenticated(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
                str(result),
            ]
        )
    assert not result.exists()
    assert children[0].returncode is not None
