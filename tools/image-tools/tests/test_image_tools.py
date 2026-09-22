from pathlib import Path

import pytest
import scripts_image_tools as images
import typer


@pytest.mark.parametrize("function,expected", [(images.twi, "twi/photo.jpg"), (images.work, "../working/photo_small.jpg")])
def test_destination_contract(function, expected, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(images.shutil, "which", lambda cmd: cmd)
    monkeypatch.setattr(images.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    function(Path("photo.png"))
    assert calls[0][-1] == expected
    assert capsys.readouterr().out.strip() == expected


def test_missing_imagemagick_fails_before_execution(monkeypatch):
    monkeypatch.setattr(images.shutil, "which", lambda cmd: None)
    with pytest.raises(typer.Exit) as exc:
        images.twi(Path("photo.png"))
    assert exc.value.exit_code == 2
