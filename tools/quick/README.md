# quick

Create a small Python, Node, C++, or empty project.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/quick
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-quick` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
quick scratch python
quick scratch empty --no-git
```

Creates projects under `~/prog/quick` unless `--base` is supplied. Names start with a letter and contain letters, digits, underscores, or hyphens. Python scaffolds require uv; Git initialization requires git unless `--no-git` is selected. Node scaffolding references tsx and tsc, which must be installed separately. stdout contains only the destination path.

## Develop

```sh
uv run --project tools/quick --locked pytest tools/quick/tests
uv build tools/quick
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
