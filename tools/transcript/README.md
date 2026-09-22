# transcript

Fetch YouTube transcripts in input order.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/transcript
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-transcript` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
transcript --terminal 'https://www.youtube.com/watch?v=VIDEO_ID'
```

Requires network access to YouTube. Progress goes to stderr and `--terminal` prints the transcript to stdout. Clipboard output needs a desktop backend. Retry behavior is unchanged by the packaging migration.

## Develop

```sh
uv run --project tools/transcript --locked pytest tools/transcript/tests
uv build tools/transcript
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
