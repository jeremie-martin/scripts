#!/usr/bin/env bash
set -euo pipefail

# ship.sh — rsync the repo to a remote host and install tools there.
#
# Usage:
#   dev/ship.sh ability@10.250.9.30                  # default dir ~/.scripts; prompts for pw if needed
#   dev/ship.sh ability@10.250.9.30 --force-password # force password/KBD-interactive auth
#   dev/ship.sh ability@10.250.9.30 --dir ~/.custom  # custom target dir
#   dev/ship.sh ability@10.250.9.30 --dry-run        # show what would sync
#   dev/ship.sh ability@10.250.9.30 --ssh-opts "-p 2222 -o StrictHostKeyChecking=no"
#
# Notes:
# - Respects .gitignore, excludes .git/, cleans stale files (but keeps excluded like .venv/).
# - Does NOT preserve mtimes → avoids clock-skew warnings from make.
# - Reuses one SSH connection (ControlMaster) to minimize repeated prompts.

REMOTE="${1:-}"
if [[ -z "${REMOTE}" || "${REMOTE}" == "--help" || "${REMOTE}" == "-h" ]]; then
  echo "Usage: dev/ship.sh <user@host> [--dir <remote_dir>] [--dry-run] [--force-password] [--no-mux] [--ssh-opts '<opts>']"
  exit 2
fi
shift || true

REMOTE_DIR="~/.scripts"
DRY_RUN=0
FORCE_PW=0
USE_MUX=1
SSH_OPTS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)           REMOTE_DIR="$2"; shift 2;;
    --dry-run)       DRY_RUN=1; shift;;
    --force-password|--password)
                     FORCE_PW=1; shift;;
    --no-mux)        USE_MUX=0; shift;;
    --ssh-opts)      SSH_OPTS+=($2); shift 2;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

# Connection sharing is configured after parsing --no-mux.
if [[ "${USE_MUX}" -eq 1 ]]; then
  mkdir -p "$HOME/.ssh"
  SSH_OPTS+=( -o ControlMaster=auto -o ControlPersist=60 -o ControlPath="$HOME/.ssh/cm-%r@%h:%p" )
fi

# Force a password prompt (disable pubkey) if requested
if [[ "${FORCE_PW}" -eq 1 ]]; then
  SSH_OPTS+=( -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive )
fi

# Resolve repo root
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Resolve remote home and expand leading ~ in REMOTE_DIR locally
# (Tilde does not expand inside quotes on the remote, so make it absolute.)
REMOTE_HOME=$(ssh "${SSH_OPTS[@]}" "${REMOTE}" 'printf %s "$HOME"')
if [[ "${REMOTE_DIR}" == '~' || "${REMOTE_DIR}" == '~/'* ]]; then
  REMOTE_DIR="${REMOTE_DIR/#\~/${REMOTE_HOME}}"
fi

# Ensure remote dir exists (ALLOW password prompt)
printf -v REMOTE_DIR_QUOTED '%q' "$REMOTE_DIR"
if [[ "${DRY_RUN}" -eq 0 ]]; then
  ssh "${SSH_OPTS[@]}" "${REMOTE}" "mkdir -p -- ${REMOTE_DIR_QUOTED}"
fi

# Build rsync (use same SSH options)
RSYNC_SSH=(ssh "${SSH_OPTS[@]}")

# Flags:
# -r  recurse
# -l  copy symlinks as symlinks
# -p  preserve permissions
# -D  preserve devices/specials (safe over ssh)
# -z  compress
# --delete  remove remote files that no longer exist locally
# IMPORTANT: we intentionally DO NOT preserve times (-t) and DO NOT --delete-excluded
RSYNC_FLAGS=(-rlpDz --protect-args --delete --partial --inplace
             --info=stats2,progress2 --human-readable
             --filter=':- .gitignore' --exclude='.git/')

[[ "${DRY_RUN}" -eq 1 ]] && RSYNC_FLAGS+=(-n) && echo ">>> DRY RUN: showing what would sync"

# Trailing slash on source to copy contents into target dir
rsync -e "${RSYNC_SSH[*]}" "${RSYNC_FLAGS[@]}" "${ROOT}/" "${REMOTE}:${REMOTE_DIR}/"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Dry run complete; no remote installation performed."
  exit 0
fi

# Post-sync: ensure uv exists and run make targets (which will also ensure PATH in rc files)
ssh "${SSH_OPTS[@]}" "${REMOTE}" "bash -s -l" <<EOF
set -euo pipefail
export PATH="\$HOME/.local/bin:\$PATH"

# Provide a fallback version for setuptools-scm when .git is absent on remote
# Prefer a PEP 440 version derived from local git describe; otherwise use timestamp+sha
_derive_version() {
  local descr count sha tag dirty ver
  descr=$(git -C "$ROOT" describe --tags --dirty --long 2>/dev/null || true)
  if [[ -n "\$descr" ]]; then
    if [[ "\$descr" == *-dirty ]]; then dirty=".dirty"; descr="\${descr%-dirty}"; else dirty=""; fi
    tag="\${descr%-*-*}"; tag="\${tag#v}"
    local rest="\${descr#\${descr%-*-*}-}"
    count="\${rest%%-*}"
    sha="\${rest#\${count}-}"; sha="\${sha#g}"
    if [[ "\$count" == 0 ]]; then ver="\${tag}\${dirty}"; else ver="\${tag}.post\${count}+g\${sha}\${dirty}"; fi
  else
    local ts sha2
    ts=$(date +%Y%m%d%H%M%S)
    sha2=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    ver="0.0.0.dev\${ts}+g\${sha2}"
  fi
  printf %s "\$ver"
}
export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SCRIPTS="\$(_derive_version)"
echo "ℹ️  Using version: \$SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SCRIPTS"

if ! command -v uv >/dev/null 2>&1; then
  echo '⚙️  Installing uv on remote (missing)...'
  curl -fsSL https://astral.sh/uv/install.sh | sh
  export PATH="\$HOME/.local/bin:\$PATH"
fi

cd -- ${REMOTE_DIR_QUOTED}
echo '📦 make sync'
make sync
echo '🔄 make retool'
make retool
EOF

echo "✅ Shipped to ${REMOTE}:${REMOTE_DIR} and refreshed tools."
