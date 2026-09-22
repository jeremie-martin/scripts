import scripts_clipboard as clipboard
import scripts_mdclip as mdclip
from typer.testing import CliRunner


def test_html_transport_uses_shared_backend(monkeypatch):
    calls = []
    monkeypatch.setattr(clipboard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name)
    monkeypatch.setattr(clipboard.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw["input"])))
    assert mdclip._copy_html_to_clipboard("<b>hi</b>", "hi", "wlcopy") == "wl-copy"
    assert len(calls) == 2
    assert all(payload == b"<b>hi</b>" for _, payload in calls)
    assert "text/html" in calls[0][0]


def test_print_html_does_not_access_clipboard(tmp_path, monkeypatch):
    source = tmp_path / "notes.md"
    source.write_text("# Heading\n\nSome **bold** text.")

    def fail(*args):
        raise AssertionError("clipboard should not be used")

    monkeypatch.setattr(mdclip, "_copy_html_to_clipboard", fail)
    result = CliRunner().invoke(mdclip.app, [str(source), "--print-html", "--title", "A & B"])
    assert result.exit_code == 0
    assert "<title>A &amp; B</title>" in result.stdout
    assert "<strong>bold</strong>" in result.stdout
