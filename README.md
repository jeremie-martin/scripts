## Scripts — utility CLIs (modern Python package)

Requires Python 3.12+ (uv will manage a matching runtime).

### Install (uv-native)
```bash
# Base
uv sync

# With extras
uv sync --extra jama
uv sync --extra media

# Both extras
uv sync --extra jama --extra media
```

### Run
Run any console script inside the project env (no manual activate needed):

```bash
uv run concat …
uv run transcript …    # needs --extra media at sync time
uv run ffcut …         # needs ffmpeg on PATH; yt-dlp provided by [media]
uv run gdiffpath …
uv run import-photos …
uv run mdclip notes.md  # copies a rendered HTML preview of the Markdown to the clipboard
uv run jamaclean …     # needs --extra jama
uv run jamaconcat …    # needs --extra jama
uv run jamaconcatfull … # needs --extra jama
uv run jamafilltests …  # needs --extra jama
uv run jamanotest …     # needs --extra jama
uv run jamatmp …        # needs --extra jama
# Linkers default to DRY RUN; pass --apply to execute
# jamaconcat*, transcript copy to clipboard by default; use -t/--terminal to print
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
uv run scripts jama clean -- ABSD-SWVER-123
uv run scripts version    # quick sanity check the install
```

### Environment
Create `.env` in project root for Jama:
```bash
JAMA_URL=https://your-instance.jamacloud.com
CLIENT_ID=…
CLIENT_SECRET=…
```

> Note: No `setup_scripts.sh` needed — entry points handle global shims.

Security note for `concat`: by default, common secret files (e.g. .env, keys, certs) are excluded. Use `--no-default-excludes` to include them.

### (Optional) Non-uv environments
Generate a `requirements.txt` from the lock for environments still on pip:
```bash
uv export --format requirements-txt -o requirements.txt   # from uv.lock
```
Then: `pip install -r requirements.txt`. (Prefer `uv sync` for day-to-day.)

### Platform notes

- mdclip: rich HTML clipboard output is implemented for Linux backends (`wl-copy`, `xclip`, `xsel`). Other platforms currently fall back to plain text.
- ffcut: `--quiet` suppresses ffmpeg/yt-dlp output.
- import-photos: `--symlinks` on Windows may require Developer Mode or admin privileges for symlink creation.

### Deploy to another machine (no GitHub access on target)

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
