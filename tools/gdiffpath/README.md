# gdiffpath

List modified non-binary Git paths. Standalone Python 3.12+; no packages are required.

```sh
ln -s "$(pwd)/tools/gdiffpath/gdiffpath" ~/.local/bin/gdiffpath
gdiffpath                 # everything changed since HEAD, staged or not
gdiffpath --staged        # only what is staged
gdiffpath HEAD~2          # what that commit changed
gdiffpath main..HEAD      # what a range changed
gdiffpath | concat        # feed the changed files to another tool
```

Requires Git on PATH and a working repository. Output paths are relative to the
current directory. Binary and deleted files are omitted. The earlier
`--target REV` spelling still works.

Tests: `uv run --no-project --with pytest pytest tools/gdiffpath/tests`.
