import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scripts import cli, ffcut, git_tools, quick

runner = CliRunner()


def test_wrapper_dispatches_without_path_lookup(monkeypatch):
    monkeypatch.setenv("PATH", "")
    original = sys.argv
    result = runner.invoke(cli.app, ["run", "concat", "--", "--help"])
    assert result.exit_code == 0
    assert "Concatenate files" in result.stdout
    assert sys.argv is original


def test_wrapper_rejects_commands_outside_package():
    result = runner.invoke(cli.app, ["run", "sh", "--", "-c", "exit 0"])
    assert result.exit_code == 2
    assert "Unknown scripts command" in result.output


def test_screenshot_help_without_desktop_dependencies(monkeypatch):
    for name in ("mss", "PIL", "pyautogui", "tkinter"):
        monkeypatch.setitem(sys.modules, name, None)
    result = runner.invoke(cli.app, ["run", "screenshot", "--", "--help"])
    assert result.exit_code == 0
    assert "selection" in result.stdout


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
    result = runner.invoke(git_tools.app, ["--staged"])
    assert result.exit_code == 0
    assert result.stdout == "../with spaces.txt\n"


def test_ffcut_help_does_not_require_ffmpeg(monkeypatch):
    monkeypatch.setattr(ffcut.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit) as exc:
        ffcut.main(["--help"])
    assert exc.value.code == 0


def test_audio_extraction_does_not_require_video_stream():
    cmd = ffcut.build_cmd("audio.mka", None, None, "out.mp3", 22, None, audio_track=1)
    assert "0:v:0" not in cmd
    assert "0:a:1" in cmd


@pytest.mark.parametrize("url", ["https://notyoutube.com/watch?v=123", "https://youtube.com.evil.invalid/watch", "/youtube.com/file"])
def test_youtube_detection_requires_real_host(url):
    assert not ffcut.is_youtube(url)


def test_download_uses_actual_merged_path(tmp_path, monkeypatch):
    monkeypatch.setattr(ffcut.os.path, "expanduser", lambda path: str(tmp_path))
    calls = []

    def downloaded(cmd, **kwargs):
        calls.append(cmd)
        return str(tmp_path / "video.mkv") + "\n"

    monkeypatch.setattr(ffcut.subprocess, "check_output", downloaded)
    assert ffcut.download_youtube("https://youtu.be/abcdefghijk") == str(tmp_path / "video.mkv")
    assert len(calls) == 1
    assert "after_move:filepath" in calls[0]


def test_ship_dry_run_does_not_install_or_create_remote_directories(tmp_path):
    # Replace external programs with spies; no SSH connection or deployment occurs.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.jsonl"
    spy = (
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['SHIP_TEST_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv) + '\\n')\n"
        "if os.path.basename(sys.argv[0]) == 'ssh':\n"
        "    print('/remote/home')\n"
    )
    for name in ("ssh", "rsync"):
        path = bin_dir / name
        path.write_text(spy)
        path.chmod(0o755)
    script = Path(__file__).resolve().parents[1] / "dev" / "ship.sh"
    result = subprocess.run(
        ["bash", str(script), "user@example.invalid", "--dry-run", "--no-mux"],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "SHIP_TEST_LOG": str(log)},
        capture_output=True,
        text=True,
        check=True,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 2
    assert calls[0][1:] == ["user@example.invalid", 'printf %s "$HOME"']
    assert "-n" in calls[1]
    assert calls[1][-1] == "user@example.invalid:/remote/home/.scripts/"
    assert "no remote installation" in result.stdout
