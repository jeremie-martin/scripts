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
