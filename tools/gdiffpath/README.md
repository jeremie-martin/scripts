# gdiffpath

List modified non-binary Git paths.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/gdiffpath
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-gdiffpath` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
gdiffpath
gdiffpath --staged
gdiffpath --target HEAD
```

Requires Git on PATH and a working repository. Output paths are relative to the current directory. Binary and deleted files are omitted.

## Develop

```sh
uv run --project tools/gdiffpath --locked pytest tools/gdiffpath/tests
uv build tools/gdiffpath
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
