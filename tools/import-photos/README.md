# import-photos

Standalone Python 3.12+ photo importer; no Python packages are required.

```sh
ln -s "$(pwd)/tools/import-photos/import_photos.py" ~/.local/bin/import-photos
import-photos --help
```

Use --dry-run before importing. Original command arguments, date grouping, conflict
policy, and symlink behavior are preserved. Originals prefer older modification
times; XMP sidecars prefer newer ones. Equal timestamps do not establish equal contents.
On Windows, symlink creation may require Developer Mode or administrator privileges.

A symlink makes edits live. For a copied install, use install -m 755 instead. Remove
only the installed link or copy to uninstall; the source stays in this directory.

Tests: `uv run --no-project --with pytest pytest tools/import-photos/tests`.
