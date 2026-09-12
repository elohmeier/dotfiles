"""Interactive per-project configuration for the sandboxed pi coding agent.

Non-secret settings are written to mise.toml (shared) or mise.local.toml
(personal, gitignored) via `mise set`. Secrets go into a sops-encrypted
.env.sops.yaml that mise decrypts at runtime through `[env] _.file`.
"""

import json
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import questionary
import rich_click as click
import yaml

SECRETS_FILE = ".env.sops.yaml"
SHARED = "mise.toml"
LOCAL = "mise.local.toml"


@dataclass
class Setting:
    var: str
    help: str
    kind: str = "str"  # str | bool | choice | secret
    choices: list[str] = field(default_factory=list)


SETTINGS = [
    Setting(
        "PI_EGRESS", "Egress filtering mode", "choice", ["allowlist", "interactive"]
    ),
    Setting(
        "PI_EGRESS_BLOCK_DNS",
        "Route DNS through the egress proxy (docker only)",
        "bool",
    ),
    Setting("PI_SSH_AGENT", "Forward the SSH agent into the container", "bool"),
    Setting("PI_LOCAL_MODELS", "Host networking for local model servers", "bool"),
    Setting("PI_NO_GITCONFIG", "Do not mount ~/.gitconfig", "bool"),
    Setting("PI_MEMORY", "Memory limit, e.g. 4g"),
    Setting("PI_CPUS", "CPU limit, e.g. 2"),
    Setting("PI_PIDS_LIMIT", "Max processes, e.g. 512"),
    Setting("PI_EXTRA_MOUNTS", "Extra mounts: src:dst[:ro|rw];..."),
    Setting(
        "PI_CONTAINER_RUNTIME", "Container runtime", "choice", ["docker", "podman"]
    ),
    Setting("ANTHROPIC_API_KEY", "Anthropic API key", "secret"),
    Setting("OPENAI_API_KEY", "OpenAI API key", "secret"),
    Setting("GEMINI_API_KEY", "Gemini API key", "secret"),
    Setting("OPENROUTER_API_KEY", "OpenRouter API key", "secret"),
]


def run(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        args, input=stdin, check=True, capture_output=True, text=True
    ).stdout


def env_table(path: str) -> dict:
    if not Path(path).exists():
        return {}
    with Path(path).open("rb") as f:
        return tomllib.load(f).get("env", {})


def secret_keys() -> list[str]:
    if not Path(SECRETS_FILE).exists():
        return []
    return list(yaml.safe_load(run("sops", "decrypt", SECRETS_FILE)))


def age_recipient() -> str:
    key_file = os.environ.get("SOPS_AGE_KEY_FILE", "~/.config/sops/age/keys.txt")
    match = re.search(r"public key: (age1\w+)", Path(key_file).expanduser().read_text())
    assert match
    return match.group(1)


def ensure_secrets_setup() -> None:
    if "_" not in env_table(SHARED):
        run("mise", "set", f"_.file={SECRETS_FILE}")
    if not Path(".sops.yaml").exists():
        Path(".sops.yaml").write_text(
            "creation_rules:\n"
            f"  - path_regex: ^{re.escape(SECRETS_FILE)}$\n"
            f"    age: {age_recipient()}\n"
        )


def ensure_gitignored(name: str) -> None:
    gitignore = Path(".gitignore")
    text = gitignore.read_text() if gitignore.exists() else ""
    if name not in text.splitlines():
        gitignore.write_text(
            text + ("" if text.endswith("\n") or not text else "\n") + name + "\n"
        )


def set_secret(var: str, value: str) -> None:
    ensure_secrets_setup()
    if Path(SECRETS_FILE).exists():
        run("sops", "set", SECRETS_FILE, f'["{var}"]', json.dumps(value))
    else:
        encrypted = run(
            "sops",
            "encrypt",
            "--input-type",
            "yaml",
            "--output-type",
            "yaml",
            "--filename-override",
            SECRETS_FILE,
            "/dev/stdin",
            stdin=yaml.safe_dump({var: value}),
        )
        Path(SECRETS_FILE).write_text(encrypted)


def unset_secret(var: str) -> None:
    if var in secret_keys():
        run("sops", "unset", SECRETS_FILE, f'["{var}"]')


def set_var(var: str, value: str, scope: str) -> None:
    if scope == LOCAL:
        ensure_gitignored(LOCAL)
    run("mise", "set", "--file", scope, f"{var}={value}")
    other = SHARED if scope == LOCAL else LOCAL
    if var in env_table(other):
        run("mise", "unset", "--file", other, var)


def unset_var(var: str) -> None:
    for path in (SHARED, LOCAL):
        if var in env_table(path):
            run("mise", "unset", "--file", path, var)


def ask_scope(current: str | None) -> str | None:
    return questionary.select(
        "Store in",
        choices=[
            questionary.Choice(f"shared ({SHARED}, committed)", SHARED),
            questionary.Choice(f"personal ({LOCAL}, gitignored)", LOCAL),
        ],
        default=current,
    ).ask()


def edit(setting: Setting, current: str | None, scope: str | None) -> None:
    var = setting.var
    if setting.kind == "secret":
        value = questionary.password(f"{var} (empty to remove)").ask()
        if value:
            set_secret(var, value)
        elif value == "":
            unset_secret(var)
    elif setting.kind == "bool":
        on = questionary.confirm(setting.help, default=current is not None).ask()
        if on and (scope := ask_scope(scope)):
            set_var(var, "1", scope)
        elif on is False:
            unset_var(var)
    else:
        if setting.kind == "choice":
            value = questionary.select(
                setting.help, choices=[*setting.choices, "(unset)"], default=current
            ).ask()
        else:
            value = questionary.text(
                f"{var} (empty to unset)", default=current or ""
            ).ask()
        if value in ("", "(unset)"):
            unset_var(var)
        elif value and (scope := ask_scope(scope)):
            set_var(var, value, scope)


@click.command()
def main() -> None:
    """Configure the sandboxed pi coding agent for the current project."""
    while True:
        shared, local, secrets = env_table(SHARED), env_table(LOCAL), secret_keys()
        choices = []
        for setting in SETTINGS:
            if setting.kind == "secret":
                current, scope = ("set" if setting.var in secrets else None), None
            elif setting.var in local:
                current, scope = str(local[setting.var]), LOCAL
            elif setting.var in shared:
                current, scope = str(shared[setting.var]), SHARED
            else:
                current, scope = None, None
            source = {LOCAL: "personal", SHARED: "shared"}.get(scope or "", "")
            title = f"{setting.var:24} {current or '—':22} {source}"
            choices.append(questionary.Choice(title, (setting, current, scope)))
        choices.append(questionary.Choice("done", "done"))

        selected = questionary.select("pi setting", choices=choices).ask()
        if selected in ("done", None):
            break
        edit(*selected)


if __name__ == "__main__":
    main()
