# Migrating the old aggregate installation

The command names remain the same, except the umbrella `scripts` command is
retired. Use each command directly and this repository's README as the catalog.

1. Save any working-tree changes and retain a copy of the old checkout. Record
   `uv tool list`; build an old wheel with `uv build` before removing its metadata
   if you need a rollback artifact. Record which extras you installed.
2. Verify the new layout with `make check`. Tests use isolated installation paths.
3. Run `uv tool uninstall scripts` to release the old command names.
4. Run `make install`, or install only the tools you use with `make install-<tool>`.
   Use `make install-screenshot-ocr` only if you want OCR.
5. Verify the commands you use. Keep the backup until satisfied.

Before installing standalone scripts, move any existing executable with that name
to a backup location. The link targets deliberately refuse collisions. Do not use
`--force` or overwrite an executable without establishing its ownership.

If migration fails, uninstall the newly installed `scripts-<tool>` distributions,
remove only the standalone links created by this migration, restore the old
checkout, and reinstall the old package with its former extras. Restore backed-up
standalone executables. A saved old wheel can also restore a non-editable install.

The old root `uv sync`, `make retool`, `make ship`, and `scripts list` workflow is
gone. Development uses `uv run --project tools/<name> --locked ...`; installation
uses `uv tool install --editable tools/<name>`. See the root README for transferring
wheels to a machine without repository access. Versions are now explicit project
versions rather than Git-derived versions; bump them when distributing releases.
