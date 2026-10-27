"""Exercise real SOPS and pass updates with generated, disposable credentials."""

import fcntl
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import secret_entry

needs_sops = pytest.mark.skipif(
    not (shutil.which("sops") and shutil.which("age-keygen")),
    reason="sops and age-keygen are required",
)
needs_pass = pytest.mark.skipif(
    not (shutil.which("pass") and shutil.which("gpg")),
    reason="pass and gpg are required",
)
INITIAL = {"EXISTING_TOKEN": "existing-dummy-value", "EMPTY_VALUE": ""}


def encrypt(path, config, data, *extra):
    path.write_bytes(
        secret_entry.sops(
            "--config",
            config,
            "encrypt",
            "--filename-override",
            path,
            "--input-type",
            "json",
            "--output-type",
            "yaml",
            *extra,
            payload=json.dumps(data).encode(),
        )
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    identity = subprocess.run(
        ["age-keygen"], capture_output=True, check=True, text=True
    ).stdout
    public = next(
        line.split(": ", 1)[1]
        for line in identity.splitlines()
        if line.startswith("# public key:")
    )
    monkeypatch.setenv("SOPS_AGE_KEY", identity)
    monkeypatch.chdir(tmp_path)
    config = tmp_path / ".sops.yaml"
    config.write_text(json.dumps({"creation_rules": [{"age": public}]}))
    path = tmp_path / "env.enc.yaml"
    encrypt(path, config, INITIAL)
    return path


def no_staging(path):
    return not list(path.parent.glob(".secret-env-*.enc.yaml"))


def run_in_terminal(argv, value, env=None):
    """Answer the hidden prompt through a real PTY and return the output."""
    master, slave = pty.openpty()
    code = "import sys; from scripts import secret_entry; sys.exit(secret_entry.main(sys.argv[1:]))"
    process = subprocess.Popen(
        [sys.executable, "-c", code, *argv],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
        env={**os.environ, **(env or {}), "PYTHONPATH": str(Path(__file__).parents[1])},
    )
    os.close(slave)
    output, entered = b"", False
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break  # A PTY reports EIO after its child closes the slave.
                if not chunk:
                    break
                output += chunk
            if b"(hidden): " in output and not entered:
                os.write(master, value + b"\n")
                entered = True
        assert entered, "The hidden prompt never appeared"
        assert process.wait(timeout=5) == 0, output
        return output
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        os.close(master)


@needs_sops
def test_round_trip_special_characters_preserves_other_values(env):
    value = "dummy ' \" : # \\ $() `not-a-command` ü"
    assert secret_entry.sops_save(env, "NEW_TOKEN", value)
    updated = env.read_bytes()
    assert value.encode() not in updated
    assert secret_entry.decrypt(env, updated) == {**INITIAL, "NEW_TOKEN": value}
    assert secret_entry.sops_contains(env, "NEW_TOKEN")
    assert not secret_entry.sops_contains(env, "EMPTY_VALUE")
    assert not secret_entry.sops_save(env, "NEW_TOKEN", value)
    assert env.read_bytes() == updated
    assert no_staging(env)


@needs_sops
def test_sops_failure_leaves_original_untouched_and_hides_diagnostics(env, monkeypatch):
    original = env.read_bytes()
    real_run = subprocess.run

    def failing_run(command, **kwargs):
        if "encrypt" in command:
            assert json.loads(kwargs["input"])["NEW_TOKEN"] == "new-dummy-value"
            assert "new-dummy-value" not in " ".join(command)
            return subprocess.CompletedProcess(
                command, 1, b"", b"secret: new-dummy-value"
            )
        return real_run(command, **kwargs)

    monkeypatch.setattr(secret_entry.subprocess, "run", failing_run)
    with pytest.raises(secret_entry.SecretError) as caught:
        secret_entry.sops_save(env, "NEW_TOKEN", "new-dummy-value")
    assert "new-dummy-value" not in str(caught.value)
    assert env.read_bytes() == original
    assert no_staging(env)


@needs_sops
def test_refuses_value_excluded_from_encryption(env):
    config = env.parent / ".sops.yaml"
    rules = json.loads(config.read_text())
    rules["creation_rules"][0]["unencrypted_suffix"] = "_PUBLIC"
    config.write_text(json.dumps(rules))
    original = env.read_bytes()
    with pytest.raises(secret_entry.SecretError, match="did not encrypt"):
        secret_entry.sops_save(env, "TOKEN_PUBLIC", "dummy-value")
    assert env.read_bytes() == original
    assert no_staging(env)


@needs_sops
def test_external_edit_is_not_overwritten(env, monkeypatch):
    real_sops = secret_entry.sops

    def concurrent_edit(*args, **kwargs):
        result = real_sops(*args, **kwargs)
        if "encrypt" in args:
            env.write_bytes(env.read_bytes() + b"\n# concurrent edit\n")
        return result

    monkeypatch.setattr(secret_entry, "sops", concurrent_edit)
    with pytest.raises(secret_entry.SecretError, match="changed during"):
        secret_entry.sops_save(env, "NEW_TOKEN", "dummy-value")
    assert env.read_bytes().endswith(b"# concurrent edit\n")
    assert b"NEW_TOKEN:" not in env.read_bytes()
    assert no_staging(env)


@needs_sops
def test_identical_plaintext_value_is_encrypted_instead_of_treated_as_noop(env):
    encrypt(
        env,
        env.parent / ".sops.yaml",
        {**INITIAL, "TOKEN_PUBLIC": "dummy-value"},
        "--unencrypted-suffix",
        "_PUBLIC",
    )
    assert b"TOKEN_PUBLIC: dummy-value" in env.read_bytes()
    assert secret_entry.sops_save(env, "TOKEN_PUBLIC", "dummy-value")
    assert b"dummy-value" not in env.read_bytes()
    assert secret_entry.decrypt(env, env.read_bytes())["TOKEN_PUBLIC"] == "dummy-value"


@needs_sops
def test_mixed_case_names_and_reserved_sops_metadata(env):
    for key in ["TF_VAR_hcloud_token", "true"]:
        assert secret_entry.sops_save(env, key, "dummy-value")
        assert secret_entry.sops_contains(env, key)
    with pytest.raises(secret_entry.SecretError):
        secret_entry.sops_save(env, "sops", "dummy-value")


@needs_sops
def test_nested_file_uses_nearest_sops_config(env):
    nested = env.parent / "clusters/production"
    nested.mkdir(parents=True)
    path = nested / ".env.enc.yaml"
    encrypt(path, env.parent / ".sops.yaml", INITIAL)
    assert secret_entry.main(["status", "--file", str(path), "EXISTING_TOKEN"]) == 0
    assert secret_entry.sops_save(path, "NEW_TOKEN", "dummy-value")
    assert secret_entry.sops_contains(path, "NEW_TOKEN")


@needs_sops
def test_another_request_holds_directory_lock(env):
    directory = os.open(env.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(secret_entry.SecretError, match="Another secret update"):
            secret_entry.sops_save(env, "NEW_TOKEN", "dummy-value")
    finally:
        os.close(directory)
    assert no_staging(env)


@needs_sops
@pytest.mark.parametrize(
    "value", ["", "two\nlines", "carriage\rreturn", "nul\x00value"]
)
def test_invalid_values_are_rejected(env, value):
    with pytest.raises(secret_entry.SecretError):
        secret_entry.sops_save(env, "NEW_TOKEN", value)


@needs_sops
def test_plaintext_and_symlinks_are_rejected(env):
    link = env.parent / "link.yaml"
    link.symlink_to(env)
    with pytest.raises(secret_entry.SecretError):
        secret_entry.sops_save(link, "NEW_TOKEN", "dummy-value")
    env.write_text("EXISTING_TOKEN: plaintext\n")
    with pytest.raises(secret_entry.SecretError):
        secret_entry.sops_save(env, "NEW_TOKEN", "dummy-value")
    assert no_staging(env)


@needs_sops
def test_status_never_prints_values_and_noninteractive_entry_fails(
    env, capsys, monkeypatch
):
    assert secret_entry.main(["status", "EXISTING_TOKEN"]) == 0
    assert secret_entry.main(["status", "MISSING_TOKEN"]) == 1
    monkeypatch.setattr(secret_entry.sys.stdin, "isatty", lambda: False)
    assert secret_entry.main(["request", "NEW_TOKEN"]) == 2
    out, err = capsys.readouterr()
    assert "existing-dummy-value" not in out + err
    assert "present" in out and "missing" in out
    assert "own terminal" in err


def test_argument_errors_do_not_echo_accidentally_supplied_secret(capsys):
    assert (
        secret_entry.main(["request", "NEW_TOKEN", "accidentally-pasted-dummy-value"])
        == 2
    )
    assert (
        secret_entry.main(["request", "--bogus=accidentally-pasted-dummy-value"]) == 2
    )
    assert "accidentally-pasted-dummy-value" not in "".join(capsys.readouterr())


@needs_sops
def test_real_terminal_entry_hides_input_and_encrypts_it(env):
    value = b"terminal-only-dummy-value"
    output = run_in_terminal(["request", "--file", str(env), "NEW_TOKEN"], value)
    assert value not in output
    assert b"saved and encryption verified" in output
    assert secret_entry.decrypt(env, env.read_bytes())["NEW_TOKEN"] == value.decode()


@pytest.fixture
def store(monkeypatch):
    # gpg-agent sockets must fit in a short Unix socket path.
    home = Path(tempfile.mkdtemp(prefix="se-", dir="/tmp"))
    gnupg = home / "gnupg"
    gnupg.mkdir(mode=0o700)
    store = home / "store"
    monkeypatch.setenv("GNUPGHOME", str(gnupg))
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(store))
    monkeypatch.delenv("PASSWORD_STORE_GPG_OPTS", raising=False)
    subprocess.run(
        [
            "gpg",
            "--batch",
            "--passphrase",
            "",
            "--quick-gen-key",
            "secret-entry-test@example.invalid",
            "default",
            "default",
            "never",
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["pass", "init", "secret-entry-test@example.invalid"],
        capture_output=True,
        check=True,
    )
    yield store
    subprocess.run(["gpgconf", "--kill", "gpg-agent"], capture_output=True, check=False)
    shutil.rmtree(home, ignore_errors=True)


def pass_show(name):
    return subprocess.run(
        ["pass", "show", name], capture_output=True, text=True, check=True
    ).stdout


@needs_pass
def test_pass_round_trip_rotates_and_reports_status(store, capsys):
    assert secret_entry.main(["status", "--pass", "team/service/token"]) == 1
    secret_entry.pass_save("team/service/token", "first-dummy-value")
    assert pass_show("team/service/token") == "first-dummy-value\n"
    secret_entry.pass_save("team/service/token", "rotated-dummy-value")
    assert pass_show("team/service/token") == "rotated-dummy-value\n"
    assert secret_entry.main(["status", "--pass", "team/service/token"]) == 0
    assert b"dummy-value" not in (store / "team/service/token.gpg").read_bytes()
    out, err = capsys.readouterr()
    assert "dummy-value" not in out + err


@needs_pass
@pytest.mark.parametrize(
    "name", ["../escape", "a/../b", ".hidden", "a//b", "/abs", "a/", "with space"]
)
def test_pass_names_cannot_escape_or_hide(store, name):
    with pytest.raises(secret_entry.SecretError):
        secret_entry.pass_save(name, "dummy-value")
    assert not list(store.rglob("*dummy*"))


@needs_pass
def test_pass_failure_hides_diagnostics(store, monkeypatch):
    (store / ".gpg-id").write_text("nobody@example.invalid\n")
    with pytest.raises(secret_entry.SecretError, match="diagnostics withheld"):
        secret_entry.pass_save("team/token", "dummy-value")
    assert not secret_entry.pass_contains("team/token")


@needs_pass
def test_pass_real_terminal_entry_hides_input(store):
    value = b"terminal-only-pass-value"
    output = run_in_terminal(["request", "--pass", "team/token"], value)
    assert value not in output
    assert b"saved in pass store" in output
    assert pass_show("team/token") == value.decode() + "\n"


@pytest.mark.parametrize("command", ["request", "status"])
def test_tpm_refuses_non_linux_before_prompt(command, monkeypatch, capsys):
    monkeypatch.setattr(secret_entry.sys, "platform", "darwin")
    monkeypatch.setattr(
        secret_entry, "prompt_secret", lambda name: pytest.fail("prompted for a secret")
    )
    assert secret_entry.main([command, "--tpm", "DUMMY_TOKEN"]) == 2
    out, err = capsys.readouterr()
    assert not out
    assert "--tpm requires Linux" in err


@pytest.mark.parametrize("unavailable", [True, False])
@pytest.mark.parametrize("option", ["--tpm", "--host"])
def test_tpm_preflight_failure_before_prompt(unavailable, option, monkeypatch, capsys):
    monkeypatch.setattr(secret_entry.sys, "platform", "linux")
    monkeypatch.setattr(
        secret_entry, "prompt_secret", lambda name: pytest.fail("prompted for a secret")
    )

    def fail(command, **kwargs):
        assert "--no-ask-password" in command
        assert kwargs["input"] == b"preflight"
        if unavailable:
            raise FileNotFoundError
        return subprocess.CompletedProcess(command, 1, b"", b"private diagnostics")

    monkeypatch.setattr(secret_entry.subprocess, "run", fail)
    assert secret_entry.main(["request", option, "DUMMY_TOKEN"]) == 2
    out, err = capsys.readouterr()
    assert not out
    assert "systemd-creds" in err
    assert "private diagnostics" not in err


def test_read_refuses_terminal_before_loading_a_secret(monkeypatch, capsys):
    monkeypatch.setattr(secret_entry.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        secret_entry, "host_secret", lambda name: pytest.fail("loaded a secret")
    )
    assert secret_entry.main(["read", "DUMMY_TOKEN"]) == 2
    out, err = capsys.readouterr()
    assert not out
    assert "Refusing" in err


@pytest.mark.parametrize("command", ["request", "status"])
@pytest.mark.parametrize(
    "options",
    [["--host", "--tpm"], ["--host", "--pass"], ["--tpm", "--file", "env.enc.yaml"]],
)
def test_conflicting_backends_fail_before_prompt(command, options, monkeypatch):
    monkeypatch.setattr(
        secret_entry, "prompt_secret", lambda name: pytest.fail("prompted for a secret")
    )
    assert secret_entry.main([command, *options, "DUMMY_TOKEN"]) == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain is required")
def test_keychain_round_trip_and_host_commands(monkeypatch, capsys):
    from keyring.backends.macOS import Keyring

    service = f"secret-entry-test-{uuid4()}"
    monkeypatch.setattr(secret_entry, "KEYCHAIN_SERVICE", service)
    try:
        assert secret_entry.host_secret("DUMMY_TOKEN") is None
        assert secret_entry.main(["status", "--host", "DUMMY_TOKEN"]) == 1
        for value in ["first-dummy-value", "rotated ' ü $() `dummy` value"]:
            monkeypatch.setattr(
                secret_entry, "prompt_secret", lambda name, value=value: value
            )
            assert secret_entry.main(["request", "--host", "DUMMY_TOKEN"]) == 0
            assert secret_entry.host_secret("DUMMY_TOKEN") == value
        assert secret_entry.main(["status", "--host", "DUMMY_TOKEN"]) == 0
        assert secret_entry.main(["read", "DUMMY_TOKEN"]) == 0
        out, err = capsys.readouterr()
        # Only the explicit pipe-only read command emits the dummy value.
        assert out.endswith(value)
        assert value not in out[: -len(value)] + err
        assert "first-dummy-value" not in out + err
    finally:
        if Keyring().get_password(service, "DUMMY_TOKEN") is not None:
            Keyring().delete_password(service, "DUMMY_TOKEN")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain is required")
def test_keychain_denied_before_prompt(monkeypatch, capsys):
    from keyring.backends.macOS import Keyring
    from keyring.errors import KeyringLocked

    def denied(*args):
        raise KeyringLocked("private diagnostics")

    monkeypatch.setattr(Keyring, "get_password", denied)
    monkeypatch.setattr(
        secret_entry, "prompt_secret", lambda name: pytest.fail("prompted for a secret")
    )
    assert secret_entry.main(["request", "--host", "DUMMY_TOKEN"]) == 2
    out, err = capsys.readouterr()
    assert not out
    assert "Keychain" in err
    assert "private diagnostics" not in err


def tpm_usable() -> bool:
    if not shutil.which("systemd-creds"):
        return False
    probe = subprocess.run(
        [
            "systemd-creds",
            "--user",
            "encrypt",
            "--with-key=host+tpm2",
            "--name=probe",
            "-",
            "-",
        ],
        input=b"x",
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


needs_tpm = pytest.mark.skipif(
    not tpm_usable(), reason="systemd-creds with a TPM2 is required"
)


@needs_tpm
def test_tpm_round_trip_is_bound_to_its_name(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert secret_entry.host_secret("DUMMY_TOKEN") is None
    assert secret_entry.main(["status", "--tpm", "DUMMY_TOKEN"]) == 1
    secret_entry.tpm_save("DUMMY_TOKEN", "first-dummy-value")
    secret_entry.tpm_save("DUMMY_TOKEN", "rotated-dummy-value")
    sealed = tmp_path / "secret-entry/DUMMY_TOKEN.cred"
    assert b"dummy-value" not in sealed.read_bytes()
    assert oct(sealed.stat().st_mode & 0o777) == "0o600"
    assert oct(sealed.parent.stat().st_mode & 0o777) == "0o700"
    assert secret_entry.host_secret("DUMMY_TOKEN") == "rotated-dummy-value"
    assert secret_entry.main(["status", "--tpm", "DUMMY_TOKEN"]) == 0
    assert secret_entry.main(["status", "--host", "DUMMY_TOKEN"]) == 0
    # The name is sealed in: a credential copied to another key does not open.
    sealed.rename(tmp_path / "secret-entry/OTHER_TOKEN.cred")
    with pytest.raises(secret_entry.SecretError, match="only opens on the host"):
        secret_entry.tpm_read("OTHER_TOKEN")
    out, err = capsys.readouterr()
    assert "dummy-value" not in out + err


@needs_tpm
def test_read_prints_for_pipes_only(tmp_path):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path)}
    os.environ["XDG_DATA_HOME"] = str(tmp_path)
    try:
        secret_entry.tpm_save("DUMMY_TOKEN", "piped-dummy-value")
    finally:
        del os.environ["XDG_DATA_HOME"]
    command = [
        sys.executable,
        "-c",
        "from scripts.secret_entry import entrypoint; entrypoint()",
    ]
    piped = subprocess.run(
        [*command, "read", "DUMMY_TOKEN"], env=env, capture_output=True, check=False
    )
    assert piped.returncode == 0 and piped.stdout == b"piped-dummy-value"
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(command[0], [*command, "read", "DUMMY_TOKEN"], env)
    output = b""
    while True:
        try:
            chunk = os.read(fd, 1024)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 2
    assert b"piped-dummy-value" not in output and b"Refusing" in output
