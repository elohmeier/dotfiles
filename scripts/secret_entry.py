"""Collect a secret in the user's own terminal and store it without echoing it.

Agents hand users `secret-entry request ...`; values never pass through chat,
arguments, or logs. Backends: a flat SOPS env file (default `env.enc.yaml` at
the git root), the pass password store, or `--tpm`: systemd-creds bound to this
host's TPM2 chip, its host key and the current user, readable without a
password by tools on this host only (`secret-entry read NAME`).
"""

import fcntl
import getpass
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import click

DEFAULT_FILE = "env.enc.yaml"


class SecretError(Exception):
    """An error whose message is safe to display."""


def validate_key(key: str) -> None:
    if key == "sops" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        raise SecretError(
            "Use a valid environment name containing letters, digits, and underscores; sops is reserved."
        )


def validate_value(value: str) -> None:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise SecretError(
            "A secret must be nonempty, single-line text without NUL characters."
        )


def sops(*args, payload: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["sops", *map(str, args)],
            input=payload,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        raise SecretError(
            "SOPS is unavailable; install it or run through mise."
        ) from None
    except subprocess.TimeoutExpired:
        raise SecretError("SOPS timed out; the file was not replaced.") from None
    if result.returncode:
        # SOPS diagnostics may contain plaintext; do not forward them.
        raise SecretError(
            "SOPS failed. Check access to the age key and encrypted file; diagnostics withheld."
        )
    return result.stdout


def read_ciphertext(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SecretError(f"{path} must be an existing regular file, not a symlink.")
    encrypted = path.read_bytes()
    try:
        status = json.loads(sops("filestatus", path))
    except (ValueError, TypeError):
        raise SecretError("Cannot verify the file's SOPS encryption status.") from None
    if status.get("encrypted") is not True:
        raise SecretError("Refusing to update an unencrypted environment file.")
    return encrypted


def decrypt(path: Path, encrypted: bytes) -> dict[str, str]:
    try:
        data = json.loads(
            sops(
                "decrypt",
                "--filename-override",
                path,
                "--input-type",
                "yaml",
                "--output-type",
                "json",
                payload=encrypted,
            )
        )
    except (ValueError, TypeError):
        raise SecretError("Cannot decode the encrypted environment.") from None
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise SecretError("Expected a flat environment mapping with string values.")
    return data


def values_are_encrypted(ciphertext: bytes, data: dict[str, str]) -> bool:
    for key, value in data.items():
        validate_key(key)
        name = key.encode()
        names = b"|".join((name, b'"' + name + b'"', b"'" + name + b"'"))
        pattern = rb"(?m)^(?:" + names + rb"): ENC\[AES256_GCM,[^\r\n]+,type:str\]$"
        if value and not re.search(pattern, ciphertext):
            return False
    return True


def sops_config(path: Path) -> Path:
    # Nearest creation rules above the file, so nested env files use their own.
    for directory in path.resolve().parents:
        if (directory / ".sops.yaml").is_file():
            return directory / ".sops.yaml"
    raise SecretError(f"No .sops.yaml governs {path}.")


def sops_contains(path: Path, key: str) -> bool:
    validate_key(key)
    return bool(decrypt(path, read_ciphertext(path)).get(key))


def sops_save(path: Path, key: str, value: str) -> bool:
    validate_key(key)
    validate_value(value)
    # Lock the directory, not the file inode replaced below. Cooperating requests
    # serialize without leaving a lock file in the working tree.
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    staged = None
    try:
        try:
            fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SecretError(
                "Another secret update is in progress. Retry when it finishes."
            ) from None
        original = read_ciphertext(path)
        previous = decrypt(path, original)
        if previous.get(key) == value and values_are_encrypted(original, previous):
            return False
        expected = {**previous, key: value}
        updated = sops(
            "--config",
            sops_config(path),
            "encrypt",
            "--filename-override",
            path,
            "--input-type",
            "json",
            "--output-type",
            "yaml",
            payload=json.dumps(expected).encode(),
        )
        # Verify every value before any output reaches disk, even if a SOPS
        # creation rule excludes selected keys from encryption. SOPS leaves
        # empty strings literal; they carry no secret to encrypt.
        if not values_are_encrypted(updated, expected):
            raise SecretError(
                "SOPS did not encrypt every value; the update was discarded."
            )
        if decrypt(path, updated) != expected:
            raise SecretError(
                "The encrypted update failed verification; the update was discarded."
            )
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".secret-env-", suffix=".enc.yaml", delete=False
        ) as temp:
            staged = Path(temp.name)
            temp.write(updated)
            temp.flush()
            os.fsync(temp.fileno())
        if path.is_symlink() or path.read_bytes() != original:
            raise SecretError(
                "The file changed during the update. Retry with its current contents."
            )
        os.chmod(staged, stat.S_IMODE(path.stat().st_mode) & 0o666)
        os.replace(staged, path)
        staged = None
        os.fsync(directory)
        return True
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
        os.close(directory)


def pass_store() -> Path:
    return Path(
        os.environ.get("PASSWORD_STORE_DIR") or Path.home() / ".password-store"
    ).expanduser()


def validate_pass_name(name: str) -> None:
    segment = r"[A-Za-z0-9_@+-][A-Za-z0-9._@+-]*"
    if not re.fullmatch(rf"{segment}(/{segment})*", name):
        raise SecretError(
            "Use a pass entry name such as team/service/token: slash-separated "
            "segments of letters, digits, and ._@+- not starting with a dot."
        )


def pass_contains(name: str) -> bool:
    validate_pass_name(name)
    return (pass_store() / f"{name}.gpg").is_file()


def pass_save(name: str, value: str) -> None:
    validate_pass_name(name)
    validate_value(value)
    try:
        result = subprocess.run(
            ["pass", "insert", "--multiline", "--force", name],
            input=f"{value}\n".encode(),
            capture_output=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        raise SecretError("pass is unavailable; install password-store.") from None
    except subprocess.TimeoutExpired:
        raise SecretError("pass timed out; the entry may not be saved.") from None
    if result.returncode or not pass_contains(name):
        raise SecretError(
            "pass failed. Check the store and its GPG recipients; diagnostics withheld."
        )


def tpm_dir() -> Path:
    data = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"
    return Path(data).expanduser() / "secret-entry"


def tpm_path(name: str) -> Path:
    validate_key(name)
    return tpm_dir() / f"{name}.cred"


def systemd_creds(*args: str, payload: bytes) -> bytes:
    try:
        result = subprocess.run(
            ["systemd-creds", "--user", *args],
            input=payload,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        raise SecretError("systemd-creds is unavailable on this host.") from None
    except subprocess.TimeoutExpired:
        raise SecretError("systemd-creds timed out.") from None
    if result.returncode:
        raise SecretError(
            "systemd-creds failed. The credential only opens on the host and for the user "
            "that stored it; diagnostics withheld."
        )
    return result.stdout


def tpm_contains(name: str) -> bool:
    return tpm_path(name).is_file()


def tpm_save(name: str, value: str) -> None:
    validate_value(value)
    path = tpm_path(name)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # --name is sealed into the credential, so a file renamed to another key fails to open.
    sealed = systemd_creds(
        "encrypt",
        "--with-key=host+tpm2",
        f"--name={name}",
        "-",
        "-",
        payload=value.encode(),
    )
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{name}-", delete=False
    ) as temp:
        temp.write(sealed)
    os.replace(temp.name, path)
    if tpm_read(name) != value:
        raise SecretError("The stored credential failed verification.")


def tpm_read(name: str) -> str:
    path = tpm_path(name)
    if not path.is_file():
        raise SecretError(
            f"{name} is not stored; run `secret-entry request --tpm {name}`."
        )
    return systemd_creds(
        "decrypt", f"--name={name}", "-", "-", payload=path.read_bytes()
    ).decode()


def host_secret(name: str) -> str | None:
    """The value stored with `secret-entry request --tpm NAME`, or None."""
    return tpm_read(name) if tpm_contains(name) else None


def prompt_secret(label: str) -> str:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SecretError(
            "Run `secret-entry request` in your own terminal; a hidden interactive prompt is required."
        )
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(f"Value for {label} (hidden): ")
        except getpass.GetPassWarning:
            raise SecretError(
                "Cannot disable terminal echo; no secret was read."
            ) from None


def env_file(file: str | None) -> Path:
    if file:
        return Path(file).absolute()
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return Path(root or ".").absolute() / DEFAULT_FILE


def shown(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


target = click.argument("name")
file_option = click.option(
    "--file",
    "file",
    help=f"SOPS env file (default: {DEFAULT_FILE} at the git root).",
)
pass_option = click.option(
    "--pass",
    "use_pass",
    is_flag=True,
    help="Use the pass password store; NAME is an entry such as team/service/token.",
)
tpm_option = click.option(
    "--tpm",
    "use_tpm",
    is_flag=True,
    help="Seal NAME with systemd-creds to this host's TPM2 and the current user.",
)


@click.group(help=__doc__)
def cli():
    pass


@cli.command(help="Prompt privately and store NAME; run it again to rotate.")
@target
@file_option
@pass_option
@tpm_option
def request(name: str, file: str | None, use_pass: bool, use_tpm: bool) -> int:
    if use_tpm:
        where = f"host credentials {tpm_dir()}"
        print(f"{'Replace' if tpm_contains(name) else 'Add'} {name} in {where}.")
        tpm_save(name, prompt_secret(name))
        print(f"{name}: sealed to this host and user, decryption verified.")
        return 0
    if use_pass:
        validate_pass_name(name)
        where = f"pass store {pass_store()}"
        print(f"{'Replace' if pass_contains(name) else 'Add'} {name} in {where}.")
        pass_save(name, prompt_secret(name))
        print(f"{name}: saved in {where}.")
        return 0
    path = env_file(file)
    present = sops_contains(path, name)
    print(f"{'Replace' if present else 'Add'} {name} in {shown(path)}.")
    changed = sops_save(path, name, prompt_secret(name))
    print(
        f"{name}: {'saved and encryption verified' if changed else 'already stored'}."
    )
    return 0


@cli.command(
    help="Report whether NAME has a value (exit 0 present, 1 missing, 2 error)."
)
@target
@file_option
@pass_option
@tpm_option
def status(name: str, file: str | None, use_pass: bool, use_tpm: bool) -> int:
    if use_tpm:
        present, where = tpm_contains(name), f"host credentials {tpm_dir()}"
    elif use_pass:
        present, where = pass_contains(name), f"pass store {pass_store()}"
    else:
        path = env_file(file)
        present, where = sops_contains(path, name), shown(path)
    print(f"{name}: {'present' if present else 'missing'} in {where}")
    return 0 if present else 1


@cli.command(
    help="Print NAME from the host credentials (--tpm) for a tool to consume, "
    "e.g. FOO_TOKEN_COMMAND='secret-entry read FOO_TOKEN'. Refuses a terminal."
)
@target
def read(name: str) -> int:
    if sys.stdout.isatty():
        raise SecretError(
            "Refusing to print a secret to a terminal; pipe it into a tool."
        )
    sys.stdout.write(tpm_read(name))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return cli.main(argv, prog_name="secret-entry", standalone_mode=False) or 0
    except click.UsageError:
        # Click's diagnostics echo unexpected arguments, possibly a pasted secret.
        print(
            "Invalid arguments. Use --help; never pass secret values as arguments.",
            file=sys.stderr,
        )
        return 2
    except click.Abort:
        print("Secret entry canceled.", file=sys.stderr)
        return 130
    except SecretError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print(
            "Secret operation failed; diagnostic details withheld to avoid exposing values.",
            file=sys.stderr,
        )
        return 2


def entrypoint() -> None:
    sys.exit(main())
