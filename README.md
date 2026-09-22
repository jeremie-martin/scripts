## Scripts — utility CLIs (modern Python package)

Requires Python 3.12+ (uv will manage a matching runtime).

### Install the tools (any machine with GitHub access)
Install all the console commands onto your PATH straight from the repo:
```bash
uv tool install git+ssh://git@github.com/jeremie-martin/scripts.git

# include the screenshot tool's deps
uv tool install 'scripts[screenshot] @ git+ssh://git@github.com/jeremie-martin/scripts.git'
```
Run a one-off without installing:
```bash
uvx --from git+ssh://git@github.com/jeremie-martin/scripts.git concat …
```

### Develop locally
```bash
# Sync a dev venv with linting and tests
uv sync --extra dev

# Install the tools in EDITABLE mode — edits to existing commands are live, no reinstall
make retool          # adds the screenshot extra
make retool-ocr      # also pulls the heavy OCR extra (torch/transformers)
```

### Run
Run any console script inside the project env (no manual activate needed):

```bash
uv run concat …
uv run transcript …    # transcript dependencies are included in the base install
uv run ffcut …         # needs ffmpeg on PATH; yt-dlp is included
uv run gdiffpath …
uv run import-photos …
uv run mdclip notes.md  # copies a rendered HTML preview of the Markdown to the clipboard
uv run screenshot selection  # interactive region capture (press 'o' for OCR if installed)
# transcript copies to clipboard by default; use -t/--terminal to print
uv run 2twi …           # ImageMagick (writes to twi/, dir must pre-exist)
uv run img-twi …        # ImageMagick (writes to twi/, dir must pre-exist)
uv run 2work …          # ImageMagick (writes to ../working/, dir must pre-exist)
uv run img-work …       # ImageMagick (writes to ../working/, dir must pre-exist)
                         # If ImageMagick is missing, the script exits with a helpful error.
```

Umbrella wrapper (optional):

```bash
uv run scripts list
uv run scripts run concat -- <args>
uv run scripts version    # quick sanity check the install
```

> Note: No `setup_scripts.sh` needed — entry points handle global shims.

Security note for `concat`: by default, common secret files (e.g. .env, keys, certs) are excluded. Use `--no-default-excludes` to include them.

`concat` applies defaults, global config, project config, then command-line options.
Explicit project values override global values, including `false` and values equal
to built-in defaults; include/exclude lists accumulate. Invalid config is an error.
`--gitignore` requires `fd` or `fdfind`; the tool refuses to silently skip ignore
rules when neither is available. Terminal concatenation emits only the requested
content and optional filename headers.

`scripts run` dispatches this package's installed entry points directly, so it
works without individual command shims on PATH. It accepts only commands shown
by `scripts list`.

`quick` project names start with a letter and contain letters, digits, hyphens,
or underscores. `--no-git` applies to Python projects as well. Its stdout contains
only the created path, for use in command substitution.

### Verification

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv build
```

The tests cover command dispatch, configuration precedence, clipboard transport,
file filtering, Git paths, scaffolding, media command construction, and deployment
dry-run behavior. Desktop services and network downloads still require manual
checks on the target machine. See [design notes](docs/design.md) for the boundaries
and remaining review areas.

### (Optional) Non-uv environments
Generate a `requirements.txt` from the lock for environments still on pip:
```bash
uv export --format requirements-txt -o requirements.txt   # from uv.lock
```
Then: `pip install -r requirements.txt`. (Prefer `uv sync` for day-to-day.)

### Platform notes

- Linux clipboard commands share backend selection: prefer `wl-copy` in a Wayland session, otherwise X11 tools. HTML and images require `wl-copy` or `xclip`; `xsel` supports plain text only. Explicit `--backend` requests never silently select a different backend.
- mdclip: rich HTML clipboard output is implemented on Linux. Other platforms currently fall back to plain text.
- ffcut: `--quiet` suppresses ffmpeg/yt-dlp output.
- import-photos: `--symlinks` on Windows may require Developer Mode or admin privileges for symlink creation.

### Deploy to a machine with no GitHub access (fallback)

If the target can't reach GitHub, push the repo over SSH instead of installing from git.
From your dev machine, rsync the repo to the target host and auto-install the `scripts` tool:

```bash
# push to default ~/.scripts on the host
dev/ship.sh ability@10.250.9.130

# or with a custom directory
dev/ship.sh ability@10.250.9.130 --dir ~/.custom-scripts

# Makefile wrapper
make ship HOST=ability@10.250.9.130
make ship HOST=ability@10.250.9.130 DIR=~/.custom-scripts
```

What it does:

* rsyncs the project (respects `.gitignore`, excludes `.venv/`, `.git/`, etc.)
* bootstraps `uv` on the remote if missing
* runs `make sync` and `make retool` remotely
* repeatable and fast for subsequent updates

`dev/ship.sh HOST --dry-run` performs the rsync preview without creating remote
directories or running remote installation commands. It still needs SSH access
to resolve the remote home directory and inspect the destination.
