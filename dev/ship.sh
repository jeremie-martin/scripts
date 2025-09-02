#!/usr/bin/env bash
set -euo pipefail

# ship.sh — rsync the repo to a remote host and install tools there.
#
# Usage:
#   dev/ship.sh ability@10.250.9.130                # default dir ~/.scripts
#   dev/ship.sh ability@10.250.9.130 --dir ~/.custom-scripts
#   dev/ship.sh ability@10.250.9.130 --dry-run      # show what would sync
#
# Requires: rsync, ssh locally; make on remote; network for uv/pypi on remote.
# Notes:    Respects .gitignore; excludes .git/ explicitly; uses --delete.

REMOTE="${1:-}"
if [[ -z "${REMOTE}" || "${REMOTE}" = "--help" || "${REMOTE}" = "-h" ]]; then
  echo "Usage: dev/ship.sh <user@host> [--dir <remote_dir>] [--dry-run]"
  exit 2
fi
shift || true

REMOTE_DIR="~/.scripts"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)      REMOTE_DIR="$2"; shift 2;;
    --dry-run)  DRY_RUN=1; shift;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

# Resolve repo root
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Ensure remote dir exists
ssh -o BatchMode=yes "${REMOTE}" "mkdir -p ${REMOTE_DIR}"

# Build rsync flags
RSYNC_FLAGS=(-az --delete --delete-excluded --partial --inplace
             --info=stats2,progress2 --human-readable
             --filter=':- .gitignore' --exclude='.git/' )

if [[ "${DRY_RUN}" -eq 1 ]]; then
  RSYNC_FLAGS+=(-n)
  echo ">>> DRY RUN: showing what would sync"
fi

# Trailing slashes matter: copy contents of ROOT/ into REMOTE_DIR/
rsync "${RSYNC_FLAGS[@]}" "${ROOT}/" "${REMOTE}:${REMOTE_DIR}/"

# On the remote:
# - ensure uv exists (install to ~/.local/bin if missing)
# - export PATH so uv is visible
# - run make targets
ssh "${REMOTE}" bash -lc "
  set -euo pipefail
  export PATH=\"\$HOME/.local/bin:\$PATH\"

  if ! command -v uv >/dev/null 2>&1; then
    echo '⚙️  Installing uv on remote (missing)...'
    curl -fsSL https://astral.sh/uv/install.sh | sh
    export PATH=\"\$HOME/.local/bin:\$PATH\"
  fi

  cd ${REMOTE_DIR}
  echo '📦 make sync'
  make sync
  echo '🔄 make retool'
  make retool
"

echo "✅ Shipped to ${REMOTE}:${REMOTE_DIR} and refreshed tools."
