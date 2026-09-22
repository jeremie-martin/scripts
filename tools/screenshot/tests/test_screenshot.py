import sys

import pytest
import scripts_screenshot as screenshot
import typer
from typer.testing import CliRunner


def test_help_without_desktop_dependencies(monkeypatch):
    for name in ("mss", "PIL", "pyautogui", "tkinter"):
        monkeypatch.setitem(sys.modules, name, None)
    result = CliRunner().invoke(screenshot.app, ["--help"])
    assert result.exit_code == 0
    assert "selection" in result.stdout


def test_copy_failure_cannot_report_success(monkeypatch, capsys):
    class Image:
        def save(self, stream, format):
            stream.write(b"image")

    def fail(*args):
        raise screenshot.ClipboardError("no desktop")

    monkeypatch.setattr(screenshot, "copy_linux", fail)
    with pytest.raises(typer.Exit) as exc:
        screenshot._copy_to_clipboard(Image())
    assert exc.value.exit_code == 1
    assert "no desktop" in capsys.readouterr().err
