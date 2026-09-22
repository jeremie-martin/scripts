from pathlib import Path

import scripts_clipboard as clipboard
import scripts_clipmedia as clipmedia
from typer.testing import CliRunner


def test_linux_transport_streams_file_to_both_selections(tmp_path, monkeypatch):
    source = tmp_path / "image.png"
    source.write_bytes(b"image payload")
    calls = []
    monkeypatch.setattr(clipboard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name)
    monkeypatch.setattr(clipboard.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw["stdin"].read())))
    assert clipmedia._copy_to_clipboard(source, "image/png", "wlcopy") == "wl-copy"
    assert len(calls) == 2
    assert all(payload == b"image payload" for _, payload in calls)
    assert "--primary" in calls[1][0]


def test_windows_path_quotes_are_escaped(monkeypatch):
    calls = []
    monkeypatch.setattr(clipmedia.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    clipmedia._copy_windows(Path("it's.png"), "image/png", None)
    assert "it''s.png" in calls[0][-1]


def test_cli_transport_failure_has_nonzero_exit(tmp_path, monkeypatch):
    source = tmp_path / "image.png"
    source.write_bytes(b"image")

    def fail(*args):
        raise clipboard.ClipboardError("no desktop")

    monkeypatch.setattr(clipmedia, "_copy_to_clipboard", fail)
    result = CliRunner().invoke(clipmedia.app, [str(source), "--mime", "image/png"])
    assert result.exit_code == 1
    assert "no desktop" in result.output
