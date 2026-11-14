import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "gdiffpath"


def test_git_paths_preserve_spaces_and_exclude_real_binary_files(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    def gdiffpath(*args):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=nested, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout

    identity = ("-c", "user.name=Test", "-c", "user.email=test@example.invalid")
    git("init", "-q")
    git(*identity, "commit", "--allow-empty", "-qm", "Initial")
    (tmp_path / "with spaces.txt").write_text("text")
    (tmp_path / "binary.dat").write_bytes(b"\0binary")
    git("add", ".")
    nested = tmp_path / "nested"
    nested.mkdir()
    assert gdiffpath("--staged") == "../with spaces.txt\n"
    assert gdiffpath() == "../with spaces.txt\n"

    git(*identity, "commit", "-qm", "Add files")
    assert gdiffpath() == ""
    assert gdiffpath("HEAD") == "../with spaces.txt\n"
    assert gdiffpath("--target", "HEAD") == "../with spaces.txt\n"
    assert gdiffpath("HEAD~1..HEAD") == "../with spaces.txt\n"


def test_outside_a_repository_fails_without_a_traceback(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
