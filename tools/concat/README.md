# concat

Concatenate text files with exclusions, configuration, and clipboard output.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/concat
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-concat` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
concat --terminal src/
concat --list .
concat --gitignore --terminal .
```

Defaults, global configuration, project configuration, then CLI options determine behavior. Explicit project scalar settings override global values; pattern lists accumulate. Config files are `~/.config/concat/config.toml` and the nearest `.concatconfig` or `.concat.toml`. Common secret files are excluded by default. `--gitignore` requires fd/fdfind; Python discovery otherwise remains available. Clipboard output needs a desktop backend; `--terminal` avoids that requirement.

## Develop

```sh
uv run --project tools/concat --locked pytest tools/concat/tests
uv build tools/concat
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
