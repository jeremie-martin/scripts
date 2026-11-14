from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

USAGE = """\
usage: ffcut INPUT [START] [END] [WORD ...] [-o FILE] [-a N] [-f] [-v] [--crf N]

Cut a file or a YouTube video, frame-accurately, into a widely playable MP4.
The output is named after the input, written to the current directory, and
its path is printed.

  INPUT                 a media file or a YouTube URL
  1:30, 1:02:03, 90,    times; the first is the start, the second the end
  1m30s, 2.5            (a lone number is seconds)
  +20s, +1:00           length, counted from the start, instead of an end
  720p                  scale down to this height (never up)
  mp3, wav, flac ...    audio only, in this format

  -o FILE   write here instead (the extension picks the format)
  -a N      use audio track N; tracks are listed when there are several
  -f        replace the output if it exists
  -v        show the ffmpeg command and its full output
  --crf N   video quality, 0 (best) to 51 (default 22)

  ffcut clip.mp4 1:30 2:45          clip_1m30-2m45.mp4
  ffcut clip.mp4 1:30 +20s 720p     clip_1m30-1m50_720p.mp4
  ffcut clip.mp4 1:30               from 1:30 to the end
  ffcut talk.mkv 0 5:00 mp3         the first five minutes of audio
  mpv "$(ffcut https://youtu.be/ID 10 25)"
"""
SHORT_USAGE = "usage: ffcut INPUT [START] [END] [720p] [mp3] [-o FILE]   (ffcut -h for help)\n"

AUDIO_CODECS = {"mp3": "libmp3lame", "aac": "aac", "wav": "pcm_s16le", "ogg": "libvorbis", "flac": "flac"}
FORMATS = {"mp4", *AUDIO_CODECS}
CLOCK = re.compile(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)")
UNITS = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?")
HEIGHT = re.compile(r"(\d+)p")


def is_youtube(s: str) -> bool:
    url = urlparse(s)
    host = url.hostname or ""
    return url.scheme in {"http", "https"} and (host in {"youtube.com", "youtu.be"} or host.endswith(".youtube.com"))


def download_youtube(url: str, quiet: bool = False) -> str:
    outdir = os.path.join(os.path.expanduser("~"), "ytmp")
    os.makedirs(outdir, exist_ok=True)
    # Ask the download operation for the actual post-merge path.
    cmd_dl = [
        sys.executable,
        "-m",
        "yt_dlp",
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


def parse_time(word: str) -> float | None:
    """Seconds for 1:30, 1:02:03, 90, 2.5, 90s, 1m30, 1h2m3s; None for anything else."""
    if clock := CLOCK.fullmatch(word):
        return int(clock[1] or 0) * 3600 + int(clock[2]) * 60 + float(clock[3])
    if word and (units := UNITS.fullmatch(word)):
        return int(units[1] or 0) * 3600 + int(units[2] or 0) * 60 + float(units[3] or 0)
    return None


def time_label(seconds: float) -> str:
    """A filename-safe time: 45s, 1m30, 1h02m03."""
    hours, rest = divmod(round(seconds, 3), 3600)
    minutes, secs = divmod(rest, 60)
    text = f"{round(secs, 3):g}"
    if hours:
        return f"{int(hours)}h{int(minutes):02}m{text.zfill(2)}"
    if minutes:
        return f"{int(minutes)}m{text.zfill(2)}"
    return f"{text}s"


@dataclass
class Request:
    source: str
    start: float | None = None
    end: float | None = None
    height: int | None = None
    format: str | None = None

    def output_name(self, input_path: str) -> str:
        parts = [os.path.splitext(os.path.basename(input_path))[0]]
        if self.start is not None or self.end is not None:
            parts.append(f"{time_label(self.start or 0)}-{time_label(self.end) if self.end is not None else 'end'}")
        if self.height and self.format not in AUDIO_CODECS:
            parts.append(f"{self.height}p")
        return f"{'_'.join(parts)}.{self.format or 'mp4'}"


def parse_words(words: list[str]) -> Request:
    """Sort words into input, times, height and format by their shape."""
    sources, times, length = [], [], None
    request = Request("")
    for word in words:
        low = word.lower()
        if low.startswith("+") and (seconds := parse_time(low[1:])) is not None:
            length = seconds
        elif (seconds := parse_time(low)) is not None:
            times.append(seconds)
        elif height := HEIGHT.fullmatch(low):
            request.height = int(height[1])
        elif low in FORMATS:
            request.format = low
        else:
            sources.append(word)

    if not sources:
        raise ValueError("give a media file or a YouTube URL")
    if len(sources) > 1:
        raise ValueError(f"unexpected word: {sources[1]} (to name the output, use -o {sources[1]})")
    request.source = sources[0]
    if not is_youtube(request.source) and not os.path.isfile(request.source):
        raise ValueError(f"no such file: {request.source}")
    if len(times) + (length is not None) > 2:
        raise ValueError("give at most a start and an end (or a +length)")
    if request.height is not None and request.height < 2:
        raise ValueError("height must be at least 2p")
    if times:
        request.start = times[0]
    if len(times) == 2:
        request.end = times[1]
    elif length is not None:
        request.start = request.start or 0.0
        request.end = request.start + length
    if request.end is not None and request.end <= (request.start or 0):
        raise ValueError("the end must come after the start")
    return request


def probe(path: str) -> tuple[float | None, list[str]]:
    """Duration in seconds and a label per audio track; (None, []) when ffprobe cannot tell."""
    entries = "format=duration:stream=codec_type,codec_name:stream_tags=language,title"
    cmd = ["ffprobe", "-v", "error", "-of", "json", "-show_entries", entries]
    try:
        info = json.loads(subprocess.check_output([*cmd, path], stderr=subprocess.DEVNULL))
        duration = float(info["format"]["duration"])
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        return None, []
    tracks = []
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            tags = stream.get("tags", {})
            tracks.append(" ".join(filter(None, [tags.get("language"), tags.get("title"), stream.get("codec_name")])))
    return duration, tracks


def build_cmd(
    inp: str,
    start: float | None,
    end: float | None,
    out: str,
    crf: int,
    scale: int | None,
    audio_track: int | None = None,
) -> list[str]:
    args = ["ffmpeg", "-nostdin", "-y"]
    if start:
        args += ["-ss", str(start)]
    if end:
        args += ["-to", str(end)]
    args += ["-i", inp]
    ext = out.rsplit(".", 1)[-1].lower()
    audio_only = ext in AUDIO_CODECS
    if audio_track is not None:
        if not audio_only:
            args += ["-map", "0:v:0"]
        args += ["-map", f"0:a:{audio_track}"]
    if audio_only:
        args += ["-vn", "-c:a", AUDIO_CODECS[ext]]
    else:
        vf = ["format=yuv420p"]
        if scale:
            vf.insert(0, f"scale=-2:'trunc(min({scale},ih)/2)*2'")  # even, and never upscaled
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


def run_ffmpeg(cmd: list[str], total: float | None, name: str, verbose: bool) -> int:
    """Run ffmpeg behind a single progress line; ffmpeg's own errors still reach stderr."""
    if verbose:
        print("running:", " ".join(cmd), file=sys.stderr)
        return subprocess.run(cmd).returncode
    show = sys.stderr.isatty()
    quiet = [cmd[0], "-loglevel", "error", "-nostats", "-progress", "pipe:1", *cmd[1:]]
    with subprocess.Popen(quiet, stdout=subprocess.PIPE, text=True) as process:
        for line in process.stdout:
            key, _, value = line.strip().partition("=")
            if show and key == "out_time_us" and value.isdigit():
                done = int(value) / 1e6
                amount = f"{min(done / total, 1):4.0%}" if total else f"{done:.0f}s"
                sys.stderr.write(f"\r\033[K\033[1m{amount}\033[0m  \033[2m{name}\033[0m")
                sys.stderr.flush()
        if show:
            sys.stderr.write("\r\033[K")
        return process.wait()


def fail(message: str, code: int = 1) -> int:
    print(f"ffcut: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ffcut", add_help=False)
    p.format_usage = lambda: SHORT_USAGE
    p.add_argument("words", nargs="*")
    p.add_argument("-o", "--output")
    p.add_argument("-a", "--audio-track", type=int, metavar="N")
    p.add_argument("-f", "--force", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--crf", type=int, default=22)
    p.add_argument("-h", "--help", action="store_true")
    a = p.parse_intermixed_args(argv)
    if a.help:
        sys.stdout.write(USAGE)
        raise SystemExit(0)
    if not a.words:
        sys.stderr.write(SHORT_USAGE)
        return 2
    if not 0 <= a.crf <= 51:
        return fail("--crf must be between 0 and 51", 2)
    if a.audio_track is not None and a.audio_track < 0:
        return fail("-a must be 0 or more", 2)
    try:
        request = parse_words(a.words)
    except ValueError as error:
        return fail(str(error), 2)
    if not shutil.which("ffmpeg"):
        return fail("ffmpeg is required on PATH (install it with your OS package manager)", 2)

    if is_youtube(request.source):
        print("ffcut: downloading…", file=sys.stderr)
        try:
            inp = download_youtube(request.source)
        except (OSError, subprocess.CalledProcessError) as error:
            return fail(f"yt-dlp download failed: {error}")
    else:
        inp = request.source

    out = a.output or request.output_name(inp)
    if os.path.exists(out):
        if os.path.samefile(out, inp):
            return fail(f"the output would replace the input; name another with -o: {out}")
        if not a.force:
            return fail(f"{out} exists (use -f to replace it)")

    duration, tracks = probe(inp)
    if a.audio_track is not None and tracks and a.audio_track >= len(tracks):
        listing = ", ".join(f"{index} {label}" for index, label in enumerate(tracks))
        return fail(f"no audio track {a.audio_track}; this file has: {listing}", 2)
    if a.audio_track is None and len(tracks) > 1:
        listing = ", ".join(f"{index} {label}" for index, label in enumerate(tracks))
        print(f"ffcut: {len(tracks)} audio tracks ({listing}); using ffmpeg's default, pick one with -a N", file=sys.stderr)
    if duration is not None and (request.start or 0) >= duration:
        return fail(f"the start is past the end of the input ({time_label(duration)})", 2)
    final = min(request.end, duration) if request.end and duration else request.end or duration
    total = final - (request.start or 0) if final else None

    cmd = build_cmd(inp, request.start, request.end, out, a.crf, request.height, a.audio_track)
    try:
        code = run_ffmpeg(cmd, total, out, a.verbose)
    except KeyboardInterrupt:
        code = 130
    except OSError as error:
        code = fail(f"could not run ffmpeg: {error}")
    if code:
        if os.path.exists(out):
            os.remove(out)  # never leave a truncated file behind
        return fail("ffmpeg failed") if code != 130 else code
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
