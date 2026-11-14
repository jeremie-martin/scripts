# quick

Create a small Python, Node, C++, or empty project. Standalone Python 3.12+; no
packages are required.

```sh
ln -s "$(pwd)/tools/quick/quick" ~/.local/bin/quick
quick scratch python
quick scratch empty --no-git
cd "$(quick idea)"
```

Creates projects under `~/prog/quick` unless `--base` is supplied. Names start with
a letter and contain letters, digits, underscores, or hyphens. An existing directory
is refused unless `--force` is given. Python scaffolds require uv; Git initialization
requires git unless `--no-git` is selected. Node scaffolding references tsx and tsc,
which must be installed separately. stdout contains only the destination path.

Tests: `uv run --no-project --with pytest pytest tools/quick/tests`.
