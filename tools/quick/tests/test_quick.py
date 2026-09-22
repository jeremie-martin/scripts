import pytest
import scripts_quick as quick
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.parametrize("name", ["../escape", "/absolute", 'bad"name', "with space"])
def test_quick_validates_before_creating_directories(tmp_path, name):
    base = tmp_path / "projects"
    result = runner.invoke(quick.app, [name, "empty", "--base", str(base), "--no-git"])
    assert result.exit_code == 2
    assert not base.exists()


def test_quick_no_git_and_clean_stdout(tmp_path):
    result = runner.invoke(quick.app, ["sample", "empty", "--base", str(tmp_path), "--no-git"])
    assert result.exit_code == 0
    assert result.stdout.strip() == str(tmp_path / "sample")
    assert not (tmp_path / "sample" / ".git").exists()


def test_python_scaffold_does_not_implicitly_initialize_git(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(quick.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))
    result = runner.invoke(quick.app, ["sample", "python", "--base", str(tmp_path), "--no-git"])
    assert result.exit_code == 0
    assert calls == [["uv", "init", "--vcs", "none", "--name", "sample", str(tmp_path / "sample")]]
