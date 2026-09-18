import json
import subprocess
import sys
import tomllib
from pathlib import Path


def test_modifier_preserves_quoted_strings_and_is_idempotent():
    modifier = (
        Path(__file__).resolve().parents[1]
        / "home/dot_codex/modify_private_config.toml.tmpl"
    ).read_text()
    modifier = modifier.replace('{{ template "theme" . }}', "cyberdream")
    modifier = modifier.replace("{{ .chezmoi.homeDir }}", "/home/test")
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

    def run(text):
        return subprocess.check_output(
            [sys.executable, "-c", modifier], input=text, text=True
        )

    rendered = run(current)
    parsed = tomllib.loads(rendered)
    assert all(parsed[key] == value for key, value in values.items())
    assert "notify" not in parsed
    assert parsed["tui"]["theme"] == "cyberdream"
    assert parsed["projects"]["/home/test/repos"]["trust_level"] == "trusted"
    assert run(rendered) == rendered
