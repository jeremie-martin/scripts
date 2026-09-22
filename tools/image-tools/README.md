# image-tools

Resize images for twi and working directories with ImageMagick.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/image-tools
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-image-tools` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
2twi photo.png
2work photo.png
```

Requires ImageMagick's convert command on PATH. `twi/` and `../working/` must already exist. `img-twi` and `img-work` are aliases for `2twi` and `2work` respectively.

## Develop

```sh
uv run --project tools/image-tools --locked pytest tools/image-tools/tests
uv build tools/image-tools
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
