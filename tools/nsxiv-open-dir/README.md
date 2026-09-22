# nsxiv-open-dir

Open an image with its neighboring images in nsxiv, or recursively open a directory.
This is a standalone Bash script. It uses GNU find, sort, and nsxiv.

```sh
ln -s "$(pwd)/tools/nsxiv-open-dir/nsxiv-open-dir" ~/.local/bin/nsxiv-open-dir
nsxiv-open-dir photo.png
nsxiv-open-dir pictures/
```

NSXIV_BIN overrides the default nsxiv executable found on PATH. Arguments and behavior
otherwise match the original local script. A symlink makes edits live; remove
only the link to uninstall. For a copied install, use install -m 755.

Tests: `uv run --no-project --with pytest pytest tools/nsxiv-open-dir/tests`.
