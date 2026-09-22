from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse


def is_youtube(s: str) -> bool:
    url = urlparse(s)
    host = url.hostname or ""
    return url.scheme in {"http", "https"} and (host in {"youtube.com", "youtu.be"} or host.endswith(".youtube.com"))


def download_youtube(url: str, quiet: bool = False) -> str:
    outdir = os.path.join(os.path.expanduser("~"), "ytmp")
    os.makedirs(outdir, exist_ok=True)
    # Ask the download operation for the actual post-merge path.
    cmd_dl = [
        "yt-dlp",
        "-q",
        "--no-warnings",
        "-f",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "-o",
        f"{outdir}/%(id)s.%(ext)s",
        "--no-playlist",
        "--print",
        "after_move:filepath",
        url,
    ]
    return subprocess.check_output(cmd_dl, text=True, stderr=subprocess.DEVNULL if quiet else None).strip()


def build_cmd(
    inp: str,
    start: str | None,
    end: str | None,
    out: str,
    crf: int,
    scale: int | None,
    audio_track: int | None = None,
) -> list[str]:
    args = ["ffmpeg", "-y"]
    if start:
        args += ["-ss", start]
    if end:
        args += ["-to", end]
    args += ["-i", inp]
    ext = out.rsplit(".", 1)[-1].lower()
    audio_only = ext in {"mp3", "aac", "wav", "ogg", "flac"}
    if audio_track is not None:
        if not audio_only:
            args += ["-map", "0:v:0"]
        args += ["-map", f"0:a:{audio_track}"]
    if audio_only:
        args += ["-vn"]
        codec = {"mp3": "libmp3lame", "aac": "aac", "wav": "pcm_s16le", "ogg": "libvorbis", "flac": "flac"}[ext]
        args += ["-c:a", codec]
    else:
        vf = ["format=yuv420p"]
        if scale:
            scale = scale // 2 * 2  # even
            vf.insert(0, f"scale=-2:{scale}")
        args += [
            "-c:v",
            "libx264",
            "-profile:v",
            "baseline",
            "-level",
            "3.1",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            str(crf),
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-metadata",
            "major_brand=mp42",
            "-metadata",
            "compatible_brands=iso6avc1mp41",
            "-strict",
            "experimental",
            "-vf",
            ",".join(vf),
        ]
    return [*args, out]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cut a time range from a file or YouTube URL (Twitter-ready MP4).")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("-ss", "--start", default=None, help="Start time (omit for beginning)")
    p.add_argument("-to", "--end", default=None, help="End time (omit for end of file)")
    p.add_argument("-crf", type=int, default=22)
    p.add_argument("-scale", type=int, default=None)
    p.add_argument(
        "-a",
        "--audio-track",
        type=int,
        default=None,
        metavar="N",
        help="Select audio track N (0-indexed, use ffprobe to list tracks)",
    )
    p.add_argument("--quiet", action="store_true", help="Hide ffmpeg/yt-dlp command echo")
    a = p.parse_args(argv)
    if not 0 <= a.crf <= 51:
        p.error("-crf must be between 0 and 51")
    if a.scale is not None and a.scale < 2:
        p.error("-scale must be at least 2")
    if a.audio_track is not None and a.audio_track < 0:
        p.error("--audio-track must be nonnegative")
    if not shutil.which("ffmpeg"):
        print("ffcut requires ffmpeg on PATH (install via your OS)", file=sys.stderr)
        return 2

    # Input validation and optional yt-dlp requirement
    if is_youtube(a.input):
        if not shutil.which("yt-dlp"):
            print("yt-dlp missing. Install it with: uv sync --extra media", file=sys.stderr)
            return 2
        try:
            inp = download_youtube(a.input, quiet=a.quiet)
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"yt-dlp download failed: {e}", file=sys.stderr)
            return 1
    else:
        if not os.path.isfile(a.input):
            print(f"Input not found: {a.input}", file=sys.stderr)
            return 2
        inp = a.input

    cmd = build_cmd(inp, a.start, a.end, a.output, a.crf, a.scale, a.audio_track)
    if not a.quiet:
        print("running:", " ".join(cmd))
    try:
        run_kwargs = {} if not a.quiet else {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        subprocess.run(cmd, check=True, **run_kwargs)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"ffmpeg failed: {e}", file=sys.stderr)
        return 1
    print("File processed:", a.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
