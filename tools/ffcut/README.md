# ffcut

Cut and encode local media or YouTube videos with ffmpeg.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/ffcut
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-ffcut` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

Name the input, then the start and the end. Everything else is optional and
words may come in any order:

```sh
ffcut clip.mp4 1:30 2:45          # writes clip_1m30-2m45.mp4
ffcut clip.mp4 1:30 +20s 720p     # 20 seconds from 1:30, scaled down to 720p
ffcut clip.mp4 1:30               # from 1:30 to the end
ffcut talk.mkv 0 5:00 mp3         # the first five minutes of audio
mpv "$(ffcut https://youtu.be/ID 10 25)"
```

| Word | Meaning |
| --- | --- |
| a file or a YouTube URL | the input |
| `1:30`, `1:02:03`, `90`, `2.5`, `1m30s` | times: the first is the start, the second the end; a lone number is seconds |
| `+20s`, `+1:00` | a length counted from the start, instead of an end |
| `720p` | scale down to this height; smaller video is never scaled up |
| `mp3`, `aac`, `wav`, `ogg`, `flac` | audio only, in this format |

The output is named after the input and what was asked, written to the current
directory, and its path is the only thing printed on standard output. A single
progress line is shown on a terminal. An existing file is not replaced, and a
failed or interrupted run leaves no partial file.

| Option | Meaning |
| --- | --- |
| `-o FILE` | write here instead; the extension picks the format |
| `-a N` | use audio track N; the tracks are listed when a file has several |
| `-f` | replace the output if it exists |
| `-v` | show the ffmpeg command and its full output |
| `--crf N` | video quality from 0 (best) to 51; the default is 22 |

Video is always re-encoded (H.264 baseline, AAC stereo, fast start), which makes
cuts frame-accurate and the result playable nearly everywhere. A stream copy
could only cut at keyframes.

Requires ffmpeg and ffprobe on PATH. yt-dlp is installed in this tool's own
Python environment and invoked through that interpreter; downloads are kept in
`~/ytmp` and named by video id. Local inputs do not require network access.
To use a file whose name looks like a time or a format, write it as a path:
`./90`.

This replaces the earlier `ffcut INPUT OUTPUT --start ... --end ...` form: the
output moved to `-o`, times became plain words, `-scale N` became `Np`, and
`--quiet` is now the default (`-v` restores the detail).

## Develop

```sh
uv run --project tools/ffcut --locked pytest tools/ffcut/tests
uv build tools/ffcut
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
