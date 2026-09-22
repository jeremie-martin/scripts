# mdclip

Render Markdown and copy styled HTML to the clipboard.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/mdclip
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-mdclip` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
mdclip notes.md
mdclip notes.md --print-html
```

HTML clipboard output requires wl-copy or xclip on Linux. Other platforms retain the plain-text fallback. `--print-html` needs no desktop clipboard.

## Develop

```sh
uv run --project tools/mdclip --locked pytest tools/mdclip/tests
uv build tools/mdclip
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
