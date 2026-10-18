#!/bin/bash
# Installs backend, test and mobile dependencies so lint, typecheck and tests
# work in Claude Code cloud sessions. Does nothing in local sessions.
#
# It runs in the background so the session starts right away. Until it
# finishes, .tmp/session-setup.status doesn't exist; then it holds the exit
# code (0 = ready). The install output is in .tmp/session-setup.log.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Claude Code reads this first line and moves the hook to the background.
echo '{"async": true, "asyncTimeout": 300000}'

cd "$CLAUDE_PROJECT_DIR"
mkdir -p .tmp
status_file=.tmp/session-setup.status
rm -f "$status_file"
trap 'echo $? > "$status_file"' EXIT
# Keep install output out of Claude's context, but keep it for when it fails.
exec > .tmp/session-setup.log 2>&1

# Set the environment first: each shell command reads this file, so the venv
# is used as soon as it exists.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/.venv\""
    echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\""
    # The pinned Playwright expects a newer Chromium build than the one the
    # cloud image ships; the smoke tests read this override.
    if [ -x /opt/pw-browsers/chromium ]; then
      echo "export AURION_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium"
    fi
  } >> "$CLAUDE_ENV_FILE"
fi

# CI runs Python 3.12; fall back to the default interpreter if it's missing.
PYTHON_BIN="$(command -v python3.12 || command -v python3)"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check \
  --require-hashes -r requirements-dev.lock

(cd mobile && npm install --no-audit --no-fund --loglevel=error)
