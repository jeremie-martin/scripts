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

```sh
ffcut input.mp4 output.mp4 --start 00:00:10 --end 00:00:20
ffcut input.mkv output.mp3 --audio-track 0
```

Requires ffmpeg on PATH. yt-dlp is installed in this tool's own Python environment and invoked through that interpreter. Local inputs do not require network access. Existing output files can be replaced. `--quiet` suppresses subprocess output.

## Develop

```sh
uv run --project tools/ffcut --locked pytest tools/ffcut/tests
uv build tools/ffcut
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
