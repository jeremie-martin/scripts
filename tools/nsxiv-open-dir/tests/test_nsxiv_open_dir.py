import json
import os
import subprocess
import sys
from pathlib import Path


def test_default_executable_uses_path(tmp_path):
    script = Path(__file__).resolve().parents[1] / "nsxiv-open-dir"
    fake = tmp_path / "nsxiv"
    fake.write_text("#!/bin/sh\nprintf 'found-on-path\\n'\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    env.pop("NSXIV_BIN", None)
    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=True)
    assert result.stdout == "found-on-path\n"


def test_image_opens_with_neighbors_including_spaces(tmp_path):
    script = Path(__file__).resolve().parents[1] / "nsxiv-open-dir"
    folder = tmp_path / "pictures with spaces"
    folder.mkdir()
    first, selected = folder / "a.png", folder / "b image.jpg"
    first.touch()
    selected.touch()
    (folder / "not an image.txt").touch()
    fake = tmp_path / "fake nsxiv"
    fake.write_text(
        f"#!{sys.executable}\nimport json, sys\nprint(json.dumps([sys.argv[1:], sys.stdin.buffer.read().decode().split('\\0')]))\n"
    )
    fake.chmod(0o755)
    result = subprocess.run(
        ["bash", str(script), str(selected)],
        env={**os.environ, "NSXIV_BIN": str(fake)},
        capture_output=True,
        text=True,
        check=True,
    )
    args, files = json.loads(result.stdout)
    assert args == ["-a", "-i", "-0", "-n", "2"]
    assert files == [str(first), str(selected), ""]
