from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

# The executable has no .py suffix, so name its loader explicitly.
loader = SourceFileLoader("quick", str(Path(__file__).resolve().parents[1] / "quick"))
quick = module_from_spec(spec_from_loader("quick", loader))
loader.exec_module(quick)


@pytest.mark.parametrize("name", ["../escape", "/absolute", 'bad"name', "with space"])
def test_quick_validates_before_creating_directories(tmp_path, name):
    base = tmp_path / "projects"
    assert quick.main([name, "empty", "--base", str(base), "--no-git"]) == 2
    assert not base.exists()


def test_quick_no_git_and_clean_stdout(tmp_path, capsys):
    assert quick.main(["sample", "empty", "--base", str(tmp_path), "--no-git"]) == 0
    assert capsys.readouterr().out == f"{tmp_path / 'sample'}\n"
    assert not (tmp_path / "sample" / ".git").exists()
    assert (tmp_path / "sample" / "README.md").read_text() == "# sample\n"


def test_existing_directory_is_kept_unless_forced(tmp_path, capsys):
    (tmp_path / "sample").mkdir()
    assert quick.main(["sample", "--base", str(tmp_path), "--no-git"]) == 1
    assert "use --force" in capsys.readouterr().err
    assert quick.main(["sample", "--base", str(tmp_path), "--no-git", "-f"]) == 0
    assert quick.main(["sample", "rust", "--base", str(tmp_path)]) == 2


def test_python_scaffold_does_not_implicitly_initialize_git(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(quick.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))
    assert quick.main(["sample", "python", "--base", str(tmp_path), "--no-git"]) == 0
    assert calls == [["uv", "init", "--vcs", "none", "--name", "sample", str(tmp_path / "sample")]]
