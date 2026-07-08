from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

YTDLP = shutil.which("yt-dlp")
FFMPEG = shutil.which("ffmpeg")

YT_RE = re.compile(r"^(https?://.*(?:youtube\.com|youtu\.be)/.*)$", re.I)


def is_youtube(s: str) -> bool:
    return bool(YT_RE.match(s))


def download_youtube(url: str) -> str:
    outdir = os.path.join(os.path.expanduser("~"), "ytmp")
    os.makedirs(outdir, exist_ok=True)
    # get final file name
    cmd_name = [YTDLP, "--get-filename", "-o", "%(id)s.%(ext)s", "--no-playlist", url]
    name = subprocess.check_output(cmd_name, text=True).strip()
    # download (1080p or below)
    cmd_dl = [
        YTDLP,
        "-q",
        "--no-warnings",
        "-f",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "-o",
        f"{outdir}/%(id)s.%(ext)s",
        "--no-playlist",
        url,
    ]
    subprocess.run(cmd_dl, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.join(outdir, name)


def build_cmd(
    inp: str,
    start: str | None,
    end: str | None,
    out: str,
    crf: int,
    scale: int | None,
    audio_track: int | None = None,
) -> list[str]:
    args = [FFMPEG, "-y"]
    if start:
        args += ["-ss", start]
    if end:
        args += ["-to", end]
    args += ["-i", inp]
    if audio_track is not None:
        args += ["-map", "0:v:0", "-map", f"0:a:{audio_track}"]
    ext = out.rsplit(".", 1)[-1].lower()
    if ext in {"mp3", "aac", "wav", "ogg", "flac"}:
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
    if not FFMPEG:
        print("ffcut requires ffmpeg on PATH (install via your OS)", file=sys.stderr)
        return 2
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

    # Input validation and optional yt-dlp requirement
    if is_youtube(a.input):
        if not YTDLP:
            print("yt-dlp missing. Install it with: uv sync --extra media", file=sys.stderr)
            return 2
        try:
            inp = download_youtube(a.input)
        except subprocess.CalledProcessError as e:
            print(f"yt-dlp download failed: {e}", file=sys.stderr)
            return 1
    else:
        if not os.path.exists(a.input):
            print(f"Input not found: {a.input}", file=sys.stderr)
            return 2
        inp = a.input

    cmd = build_cmd(inp, a.start, a.end, a.output, a.crf, a.scale, a.audio_track)
    if not a.quiet:
        print("running:", " ".join(cmd))
    try:
        run_kwargs = {} if not a.quiet else {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        subprocess.run(cmd, check=True, **run_kwargs)
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg failed: {e}", file=sys.stderr)
        return 1
    print("File processed:", a.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
