#!/bin/bash
# Installs backend, test and mobile dependencies so lint, typecheck and tests
# work in Claude Code cloud sessions. Does nothing in local sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# SessionStart stdout is added to Claude's context; keep install noise out of it.
exec 1>&2

cd "$CLAUDE_PROJECT_DIR"

# CI runs Python 3.12; fall back to the default interpreter if it's missing.
PYTHON_BIN="$(command -v python3.12 || command -v python3)"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check \
  --require-hashes -r requirements-dev.lock

(cd mobile && npm install --no-audit --no-fund --loglevel=error)

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/.venv\""
    echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\""
    # The pinned Playwright expects a newer Chromium build than the one the
    # cloud image ships; tests/test_frontend_smoke.py reads this override.
    if [ -x /opt/pw-browsers/chromium ]; then
      echo "export AURION_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium"
    fi
  } >> "$CLAUDE_ENV_FILE"
fi
