# Personal command-line tools

Small tools that live together but install independently. There is no umbrella
application, shared runtime environment, or deployment service.

| Tool | Purpose |
| --- | --- |
| [concat](tools/concat/) | Collect source files for a prompt |
| [transcript](tools/transcript/) | Fetch video transcripts |
| [ffcut](tools/ffcut/) | Download and cut media |
| [gdiffpath](tools/gdiffpath/) | Inspect Git changes by path |
| [clipmedia](tools/clipmedia/) | Copy media to the clipboard |
| [mdclip](tools/mdclip/) | Copy Markdown as rich text |
| [quick](tools/quick/) | Create a small project |
| [screenshot](tools/screenshot/) | Capture screens, optionally with OCR |
| [agent-export](tools/agent-export/) | Export agent conversations |
| [image-tools](tools/image-tools/) | Image conversion: 2twi, 2work, img-twi, img-work |
| [import-photos](tools/import-photos/) | Import photographs |
| [ssh-clipboard](tools/ssh-clipboard/) | Transfer clipboard content over SSH |
| [nsxiv-open-dir](tools/nsxiv-open-dir/) | Open an image's directory in nsxiv |

## Install and update

For a Python tool, use its project directly:

```sh
uv tool install --editable ./tools/concat
concat --help
```

Each tool has its own uv-managed environment. Source edits are live; after
dependency or entry-point changes, repeat with `--reinstall`. Update this
checkout with Git before reinstalling; `uv tool upgrade` does not pull Git.
Uninstall with `uv tool uninstall scripts-concat`.

These are ordinary [uv tool installations](https://docs.astral.sh/uv/concepts/tools/),
not a repository-specific installation mechanism.

The optional Makefile runs these native commands:

```sh
make install-concat
make install                      # all tools, without OCR
make install-screenshot-ocr        # explicitly opt into heavy OCR dependencies
```

Standalone tools are symlinked into `uv tool dir --bin`. Set `BINDIR` to
override it. These Make targets require GNU ln and refuse existing unrelated
files or links. Remove a standalone tool's symlink to uninstall it.
You can also link or copy the executable yourself; see its README.
System programs such as ffmpeg and desktop clipboard utilities are not installed
automatically.

If you previously installed the aggregate `scripts` package, follow
[the migration instructions](docs/migration.md) first to avoid command collisions.

Python clipboard consumers declare the small [clipboard library](packages/clipboard/)
as an editable relative-path dependency. Moving the checkout requires reinstalling.
Omitting `--editable` alone does **not** detach that dependency; use wheels when
you need an installation independent of the checkout.

## Occasional installation without Git access

Build the tool and its local library, then transfer the wheels:

```sh
uv build packages/clipboard --out-dir dist
uv build tools/concat --out-dir dist
# On the other machine, with transferred wheels in ./wheels:
uv tool install --find-links ./wheels ./wheels/scripts_concat-0.1.0-py3-none-any.whl
```

Use `--reinstall` to replace an existing same-version installation. Tools without
the clipboard dependency need only their own wheel. Third-party dependencies
still require network access; a fully offline install also needs compatible
dependency wheels and an available Python interpreter, using
`--offline --no-index --find-links ./wheels`. Standalone tools can simply be
copied. There is no special remote deployment protocol.

## Develop and verify

```sh
uv run --project tools/concat --locked pytest tools/concat/tests
make lint
make test
make test-installation
make build
```

Development environments and lockfiles belong to each project. Lockfiles govern
`uv run --locked`, not `uv tool install`. Installation tests build and install
tools in temporary directories, independently of the live installation.
`make check` runs all checks. Tests do not require a live desktop or remote host.

Add a small tool with its source, README, dependencies (if any), and tests.
Choose the simplest native installation: a symlink, `uv tool install`, or
`go install` for a Go project. There is no mandatory CLI framework or registry.
Large applications belong in their own repositories. See [design notes](docs/design.md).
