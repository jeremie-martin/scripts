# screenshot

Capture the desktop, a monitor, or an interactive selection.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/screenshot
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-screenshot` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
screenshot selection
screenshot full
screenshot monitor 1
```

Requires an accessible desktop and system Tk support for interactive selection. Python capture dependencies are included in the ordinary install. Linux clipboard output requires wl-copy or xclip. Capture state remains in the existing XDG cache location. OCR is optional and downloads model data when used.

Enable OCR explicitly:

```sh
uv tool install --reinstall --editable 'tools/screenshot[ocr]'
```

This installs Torch and Transformers only for screenshot. Use the same command
without `[ocr]` to return to the ordinary capture installation.

## Develop

```sh
uv run --project tools/screenshot --locked pytest tools/screenshot/tests
uv build tools/screenshot
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
