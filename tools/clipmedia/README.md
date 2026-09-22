# clipmedia

Copy files to the desktop clipboard with MIME detection.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/clipmedia
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-clipmedia` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
clipmedia picture.png
clipmedia picture.png --backend wl-copy
```

Linux requires wl-copy or xclip for arbitrary MIME types; xsel supports plain text only. macOS uses osascript (or explicitly requested pbcopy); Windows uses PowerShell. `--mime` overrides MIME detection and `--backend` selects an installed backend.

## Develop

```sh
uv run --project tools/clipmedia --locked pytest tools/clipmedia/tests
uv build tools/clipmedia
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
