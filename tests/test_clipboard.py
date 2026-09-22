import subprocess
from pathlib import Path

import pytest

from scripts import clipboard, clipmedia, mdclip


@pytest.fixture
def calls(monkeypatch):
    recorded = []
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(clipboard.subprocess, "run", lambda cmd, **kwargs: recorded.append((cmd, kwargs)))
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    return recorded


def test_active_display_and_both_selections(calls, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert clipboard.copy_linux(b"hello") == "wl-copy"
    assert len(calls) == 2
    assert "--primary" not in calls[0][0]
    assert "--primary" in calls[1][0]
    assert all(kwargs["input"] == b"hello" for _, kwargs in calls)


def test_explicit_backend_wins_over_display(calls, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert clipboard.copy_linux(b"hello", backend="xclip") == "xclip"
    assert [cmd[2] for cmd, _ in calls] == ["clipboard", "primary"]


@pytest.mark.parametrize("mime", ["image/png", "text/html"])
def test_xsel_rejects_rich_payloads(calls, mime):
    with pytest.raises(clipboard.ClipboardError, match="plain text only"):
        clipboard.copy_linux(b"payload", mime, "xsel")
    assert not calls


def test_missing_explicit_backend_does_not_fall_back(calls, monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: None if name == "wl-copy" else name)
    with pytest.raises(clipboard.ClipboardError):
        clipboard.copy_linux(b"hello", backend="wlcopy")
    assert not calls


def test_process_failure_identifies_selection(calls, monkeypatch):
    def fail(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(clipboard.subprocess, "run", fail)
    with pytest.raises(clipboard.ClipboardError, match="xclip failed copying to clipboard"):
        clipboard.copy_linux(b"hello")


def test_files_are_reopened_for_each_selection(tmp_path, monkeypatch):
    source = tmp_path / "picture.png"
    source.write_bytes(b"image payload")
    payloads = []
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name)
    monkeypatch.setattr(clipboard.subprocess, "run", lambda cmd, **kwargs: payloads.append(kwargs["stdin"].read()))
    clipboard.copy_linux(source, "image/png", "xclip")
    assert payloads == [b"image payload", b"image payload"]


def test_rich_commands_share_transport(calls, monkeypatch, tmp_path):
    monkeypatch.setattr(clipboard.platform, "system", lambda: "Linux")
    source = tmp_path / "image.png"
    source.write_bytes(b"image")
    assert clipmedia._copy_to_clipboard(source, "image/png", "wlcopy") == "wl-copy"
    assert mdclip._copy_html_to_clipboard("<b>hi</b>", "hi", "wlcopy") == "wl-copy"
    assert calls[-1][1]["input"] == b"<b>hi</b>"


def test_windows_path_quotes_are_escaped(calls):
    clipmedia._copy_windows(Path("it's.png"), "image/png", None)
    assert "it''s.png" in calls[0][0][-1]
