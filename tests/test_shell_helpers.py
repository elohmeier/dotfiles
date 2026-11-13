import subprocess
import sys
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner

from scripts import getsubs, theme, timing

VTT = """WEBVTT

00:00:00.000 --> 00:00:01.000
<c>Hello &amp; welcome.</c>

00:00:01.000 --> 00:00:02.000
Hello &amp; welcome.
<00:00:01.500><c>Second line.</c>

"""


@pytest.mark.parametrize("automatic", [False, True])
def test_getsubs_prefers_official_and_falls_back(monkeypatch, automatic):
    calls = []

    def download(args, **kwargs):
        calls.append(args)
        if not automatic or "--write-auto-subs" in args:
            output = Path(args[args.index("--output") + 1]).parent
            (output / "video.de.vtt").write_text(VTT)

    monkeypatch.setattr(getsubs.subprocess, "run", download)
    result = CliRunner().invoke(getsubs.main, ["--lang", "de", "https://example.com"])
    assert result.exit_code == 0, result.output
    assert result.output == "Hello & welcome.\nSecond line.\n"
    assert "--write-subs" in calls[0]
    assert len(calls) == (2 if automatic else 1)


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("has_themed_files", [False, True])
def test_theme_preserves_config_and_only_applies_themed_files(
    tmp_path, monkeypatch, dry_run, has_themed_files
):
    config = tmp_path / "chezmoi.toml"
    original = '# keep this comment\nencryption = "age"\n[data]\ntheme = "tokyonight_day"\nname = "Enno"\n'
    config.write_text(original)
    themed = tmp_path / "config.tmpl"
    themed.write_text('{{ template "theme" . }}')
    install = tmp_path / "run_onchange_after_install.sh.tmpl"
    install.write_text("#!/bin/sh\ninstall-everything\n")

    def output(args, **kwargs):
        if "execute-template" in args:
            return str(config)
        return f"{themed}\n{install}\n" if has_themed_files else f"{install}\n"

    applied = []
    monkeypatch.setattr(theme.subprocess, "check_output", output)
    monkeypatch.setattr(
        theme.subprocess, "run", lambda args, **kwargs: applied.extend(args)
    )
    args = ["cyberdream", *(["--dry-run"] if dry_run else [])]
    result = CliRunner().invoke(theme.main, args)
    assert result.exit_code == 0, result.output
    assert (str(themed) in applied) == has_themed_files
    assert str(install) not in applied
    if not has_themed_files:
        assert not applied
    assert config.read_text() == (
        original if dry_run else original.replace('"tokyonight_day"', '"cyberdream"')
    )


@pytest.mark.parametrize(
    "duration,seconds", [("10m", 600), ("1.5h", 5400), ("0.2", 0.2)]
)
def test_timer_waits_then_notifies(monkeypatch, duration, seconds):
    events = []
    monkeypatch.setattr(timing.time, "sleep", lambda value: events.append(value))
    monkeypatch.setattr(timing, "notify", lambda *args: events.append(args))
    result = CliRunner().invoke(timing.timer, [duration])
    assert result.exit_code == 0, result.output
    assert events == [seconds, ("Timer", f"{duration} timer complete")]


def test_waitfor_observes_exit_without_claiming_process_success(monkeypatch):
    messages = []
    monkeypatch.setattr(timing.shutil, "which", lambda name: None)
    monkeypatch.setattr(timing, "notify", lambda *args: messages.append(args))
    with subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(0.05); raise SystemExit(7)"]
    ) as process:
        reaper = threading.Thread(target=process.wait)
        reaper.start()
        result = CliRunner().invoke(timing.waitfor, ["--notify", str(process.pid)])
        reaper.join()
    assert result.exit_code == 0, result.output
    assert process.returncode == 7
    assert messages == [("Process", f"PID {process.pid} exited")]
