import subprocess

import scripts_gdiffpath as gdiffpath
from typer.testing import CliRunner

runner = CliRunner()


def test_git_paths_preserve_spaces_and_exclude_real_binary_files(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "Initial")
    (tmp_path / "with spaces.txt").write_text("text")
    (tmp_path / "binary.dat").write_bytes(b"\0binary")
    git("add", ".")
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    result = runner.invoke(gdiffpath.app, ["--staged"])
    assert result.exit_code == 0
    assert result.stdout == "../with spaces.txt\n"
