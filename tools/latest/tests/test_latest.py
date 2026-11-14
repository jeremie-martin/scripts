import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "latest"
NOW = time.time()


def make(root, path, age=0, content=""):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content)
    os.utime(file, (NOW - age, NOW - age))


def latest(cwd, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True)


def paths(cwd, *args):
    result = latest(cwd, *args)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_lists_everything_newest_last_and_skips_hidden(tmp_path):
    make(tmp_path, "old.txt", age=500)
    make(tmp_path, "build/new.mp4", age=5)
    make(tmp_path, "mid.PNG", age=50)
    make(tmp_path, ".cache/hidden.png")
    assert paths(tmp_path) == ["old.txt", "mid.PNG", "build/new.mp4"]
    assert paths(tmp_path, "-H")[-1] == ".cache/hidden.png"


def test_extensions_and_kinds_combine_case_insensitively(tmp_path):
    for age, name in enumerate(["a.mp4", "b.MKV", "c.png", "d.csv", "mp4", "e.jpeg"]):
        make(tmp_path, name, age=age)
    assert paths(tmp_path, "mp4") == ["a.mp4"]
    assert paths(tmp_path, "video") == ["b.MKV", "a.mp4"]
    assert paths(tmp_path, "img", ".csv") == ["e.jpeg", "d.csv", "c.png"]


def test_count_age_and_all_in_any_order(tmp_path):
    for index in range(15):
        make(tmp_path, f"{index:02}.png", age=index * 3600)
    assert paths(tmp_path)[0] == "09.png"
    assert len(paths(tmp_path, "all")) == 15
    assert paths(tmp_path, "2", "png") == ["01.png", "00.png"]
    assert paths(tmp_path, "png", "150m") == ["02.png", "01.png", "00.png"]
    assert paths(tmp_path, "1d", "png", "1") == ["00.png"]


def test_directories_keep_the_spelling_given(tmp_path):
    make(tmp_path, "build/a.png", age=1)
    make(tmp_path, "out/sub/b.png", age=2)
    make(tmp_path, "c.png", age=3)
    assert paths(tmp_path, "png", "build", "out") == ["out/sub/b.png", "build/a.png"]
    assert paths(tmp_path, str(tmp_path / "out")) == [str(tmp_path / "out/sub/b.png")]


def test_known_type_wins_over_directory_unless_written_as_path(tmp_path):
    make(tmp_path, "png/notes.txt", age=1)
    make(tmp_path, "csv/notes.txt", age=1)
    make(tmp_path, "shot.png", age=2)
    assert paths(tmp_path, "png") == ["shot.png"]
    assert paths(tmp_path, "./png") == ["png/notes.txt"]
    assert paths(tmp_path, "csv") == ["csv/notes.txt"]


def test_no_match_explains_the_interpretation(tmp_path):
    make(tmp_path, "a.png", age=7200)
    result = latest(tmp_path, "biuld")
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == "latest: no biuld files under .\n"
    assert latest(tmp_path, "png", "1h").stderr == "latest: no png files under . modified in the last 1h\n"


def test_bad_words_are_usage_errors(tmp_path):
    for word, message in [("missing/dir", "no such directory: missing/dir"), ("0", "count must be at least 1")]:
        result = latest(tmp_path, word)
        assert result.returncode == 2
        assert message in result.stderr


def test_long_listing_and_nul_output(tmp_path):
    make(tmp_path, "sub/a b.png", age=90, content="x" * 2048)
    make(tmp_path, "old.png", age=400 * 86400)
    make(tmp_path, "c.png", age=3 * 3600)
    lines = paths(tmp_path, "-l", "2")
    assert lines[0].strip() == "… 1 more"
    assert lines[1].split()[0] == "3h"
    assert lines[2].split()[0] == "1m"
    assert lines[2].endswith("  2.0K  sub/a b.png")
    assert "\033" not in "".join(lines)
    assert paths(tmp_path, "-l", "all")[0].split()[0] == "1y"
    assert latest(tmp_path, "-0", "2").stdout == "c.png\0sub/a b.png\0"


def test_does_not_follow_directory_symlinks(tmp_path):
    make(tmp_path, "real/a.png")
    (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)
    assert paths(tmp_path) == ["real/a.png"]
