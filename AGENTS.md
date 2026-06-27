# Repository Guidelines

## Project Structure & Module Organization
- Source: `src/scripts/` (Typer-based CLIs; entry points defined in `pyproject.toml`).
- Packaging: standard setuptools with setuptools-scm; wheel/sdist output in `dist/`.
- Tooling: `Makefile` tasks (`retool`, `sync`, `ship`, `clean`), `uv.lock` for deps, optional `.venv/`.
- Dev utilities: `dev/ship.sh` for rsync-based deployment to a remote host.

## Build, Test, and Development Commands
- Install deps: `uv sync` (add extras as needed: `--extra dev`, `--extra media`, `--extra screenshot`, `--extra ocr`).
- Install console tools locally: `make retool` (editable `uv tool` install — edits to existing commands are live; `make retool-ocr` also pulls the OCR extra).
- Run a command in the env: `uv run concat …` or `uv run scripts list`.
- Lint: `uv sync --extra dev && uv run ruff check .` (add `--fix` to auto-fix).
- Build artifacts: `uv build` (creates sdist/wheel under `dist/`).
- Deploy to host: `make ship HOST=user@host [DIR=~/.scripts]`.

## Coding Style & Naming Conventions
- Language: Python 3.12+. Use type hints, f-strings, and 4-space indentation.
- Linting: Ruff with `line-length = 140` and rules `E,F,I,B,UP,SIM,RUF` (see `pyproject.toml`).
- Modules: snake_case files in `src/scripts/` (e.g., `git_tools.py` → command `gdiffpath`).
- CLIs: Typer apps; prefer clear, long-form option names; default to safe modes (`--dry-run`, clipboard) where applicable.
- Entry points: each console script targets `module:main`, where `main` is a launcher (`def main(): app()` for Typer apps; the argparse entry for the rest). Exception: `img_tools` exposes two binaries via `cmd_2twi`/`cmd_2work`.

## Testing Guidelines
- No formal test suite yet. Validate changes by running commands with sample inputs and using built-in dry-run flags.
- If adding tests, prefer `pytest` under `tests/` with files named `test_*.py`; ensure new utilities have minimal usage examples.

## Commit & Pull Request Guidelines
- Messages: imperative tone and concise scope. Conventional prefixes welcome (`feat:`, `fix:`, `docs:`, `chore:`) as seen in history.
- PRs: include what/why, notable flags or behavior changes, and example invocations. Link related issues or tickets.
- Scope: keep PRs small and focused; update `README.md` when adding commands or flags.

## Security & Configuration Tips
- Secrets: the `concat` tool excludes common secret files (`.env`, keys, certs) by default; override with care.
- External tools: some commands require system binaries (e.g., `ffmpeg`, ImageMagick). Document platform nuances in PRs impacting these.
