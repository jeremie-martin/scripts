import sys

import pytest
import scripts_ffcut as ffcut


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
    assert calls[0][:3] == [sys.executable, "-m", "yt_dlp"]
    assert "after_move:filepath" in calls[0]


@pytest.mark.parametrize(
    ("word", "seconds"),
    [("90", 90), ("2.5", 2.5), ("1:30", 90), ("1:02:03.5", 3723.5), ("90s", 90), ("1m30", 90), ("1h2m3s", 3723), ("5m", 300)],
)
def test_times_are_understood_in_common_spellings(word, seconds):
    assert ffcut.parse_time(word) == seconds


@pytest.mark.parametrize("word", ["", "720p", "mp3", "clip.mp4", "1:2:3:4", "abc"])
def test_other_words_are_not_times(word):
    assert ffcut.parse_time(word) is None


def test_words_are_sorted_by_shape_and_name_the_output(tmp_path):
    clip = tmp_path / "my clip.mkv"
    clip.touch()
    request = ffcut.parse_words(["720p", str(clip), "1:30", "+20s"])
    assert (request.start, request.end, request.height, request.format) == (90, 110, 720, None)
    assert request.output_name(request.source) == "my clip_1m30-1m50_720p.mp4"
    assert ffcut.parse_words([str(clip), "1:02:03"]).output_name(str(clip)) == "my clip_1h02m03-end.mp4"
    assert ffcut.parse_words([str(clip), "0", "2.5", "MP3", "720p"]).output_name(str(clip)) == "my clip_0s-2.5s.mp3"
    assert ffcut.parse_words(["https://youtu.be/abcdefghijk", "+10"]).end == 10
    assert ffcut.parse_words([str(clip), "flac"]).output_name(str(clip)) == "my clip.flac"


@pytest.mark.parametrize(
    ("words", "message"),
    [
        (["1:30"], "give a media file"),
        (["clip.mkv", "out.mp4"], "use -o out.mp4"),
        (["missing.mkv"], "no such file: missing.mkv"),
        (["clip.mkv", "1", "2", "3"], "at most a start and an end"),
        (["clip.mkv", "1", "2", "+3"], "at most a start and an end"),
        (["clip.mkv", "5", "3"], "end must come after the start"),
    ],
)
def test_unclear_requests_are_rejected(tmp_path, monkeypatch, words, message):
    (tmp_path / "clip.mkv").touch()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=message):
        ffcut.parse_words(words)


def test_video_is_never_upscaled_and_cut_points_reach_ffmpeg():
    cmd = ffcut.build_cmd("in.mkv", 90.0, 110.0, "out.mp4", 22, 720)
    assert cmd[cmd.index("-ss") + 1] == "90.0"
    assert cmd[cmd.index("-to") + 1] == "110.0"
    assert cmd[cmd.index("-vf") + 1] == "scale=-2:'trunc(min(720,ih)/2)*2',format=yuv420p"


def run_main(monkeypatch, tmp_path, args, code=0):
    """Run main with ffmpeg replaced by a stub that creates the output file."""
    commands = []

    def fake_ffmpeg(cmd, total, name, verbose):
        commands.append(cmd)
        open(cmd[-1], "w").close()
        return code

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ffcut.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffcut, "probe", lambda path: (60.0, ["eng aac", "fra aac"]))
    monkeypatch.setattr(ffcut, "run_ffmpeg", fake_ffmpeg)
    return ffcut.main(args), commands


def test_main_prints_only_the_output_path_and_refuses_to_overwrite(tmp_path, monkeypatch, capsys):
    (tmp_path / "clip.mkv").touch()
    status, commands = run_main(monkeypatch, tmp_path, ["clip.mkv", "10", "25"])
    assert status == 0
    assert commands[0][-1] == "clip_10s-25s.mp4"
    captured = capsys.readouterr()
    assert captured.out == "clip_10s-25s.mp4\n"
    assert "2 audio tracks (0 eng aac, 1 fra aac)" in captured.err

    status, commands = run_main(monkeypatch, tmp_path, ["clip.mkv", "10", "25"])
    assert (status, commands) == (1, [])
    assert "exists (use -f to replace it)" in capsys.readouterr().err
    assert run_main(monkeypatch, tmp_path, ["clip.mkv", "10", "25", "-f"])[0] == 0
    assert run_main(monkeypatch, tmp_path, ["clip.mkv", "-o", "clip.mkv"]) == (1, [])


def test_main_removes_partial_output_and_validates_against_the_input(tmp_path, monkeypatch, capsys):
    (tmp_path / "clip.mkv").touch()
    status, _ = run_main(monkeypatch, tmp_path, ["clip.mkv", "10", "-o", "out.mp4"], code=1)
    assert status == 1
    assert not (tmp_path / "out.mp4").exists()
    assert run_main(monkeypatch, tmp_path, ["clip.mkv", "90"]) == (2, [])
    assert run_main(monkeypatch, tmp_path, ["clip.mkv", "-a", "2"]) == (2, [])
    assert "no audio track 2; this file has: 0 eng aac, 1 fra aac" in capsys.readouterr().err
