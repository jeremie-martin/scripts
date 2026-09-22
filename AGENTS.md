# Working in this repository

This is a collection of independent tools, not a Python application or workspace.
Read the owning tool's README before changing it.

- Tool code, dependencies, lockfile, documentation, and unit tests belong in
  `tools/<name>/`. Python projects use native editable uv tool installs.
- `packages/clipboard/` owns the explicitly declared shared clipboard library.
  `ssh-clipboard` must remain standalone: it sends its own source over SSH and
  supports Python 3.8+. Other Python tools require Python 3.12+.
- Preserve command names, data formats, and unrelated working-tree changes.
  Do not import another tool or rely on a root development environment.
- After dependency changes, update the owning project's lockfile.
  Run `uv run --project tools/<name> --locked pytest tools/<name>/tests`.
- Run `make lint`; for packaging changes also run `make test-installation`.
  Installation tests must isolate UV_TOOL_DIR and UV_TOOL_BIN_DIR. Changing the
  user's installed tools is a separate, user-visible operation.
- Wheels must work without this checkout or Git. OCR dependencies belong only
  to screenshot's explicit extra. Mock network, clipboard, and user-file effects
  in tests; do not exercise them against live services.
- Add new commands to the root catalog with their native install instructions.
  Shell, standalone Python, and Go tools need not adopt Python packaging.
- Keep commits focused and describe behavior changes and verification.
