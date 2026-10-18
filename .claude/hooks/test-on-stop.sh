#!/bin/bash
# When Claude finishes a turn with uncommitted changes, runs the fast checks
# for what changed and sends any failures back to Claude:
#   backend/  mypy and the backend tests
#   tests/    the backend tests
#   mobile/   the TypeScript typecheck
# The Playwright smoke tests are left to CI and to running them by hand.
set -euo pipefail

# If this hook already sent Claude back once, let it stop instead of looping.
if python3 -c 'import json, sys; sys.exit(0 if json.load(sys.stdin).get("stop_hook_active") else 1)'; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# In cloud sessions, don't check against a half-installed environment while
# the startup hook is still running in the background.
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && [ ! -f .tmp/session-setup.status ]; then
  exit 0
fi

changed() { [ -n "$(git status --porcelain -- "$@" 2>/dev/null)" ]; }

failures=""
check() {
  local name="$1" output
  shift
  if ! output="$("$@" 2>&1)"; then
    failures+="$name failed:"$'\n'"$(echo "$output" | tail -n 40)"$'\n\n'
  fi
}

if changed backend tests; then
  if [ -x .venv/bin/python ]; then
    python=.venv/bin/python
  else
    python=python3
  fi
  # Skip quietly when the Python dependencies aren't installed.
  if "$python" -c "import fastapi, mypy, pytest" 2>/dev/null; then
    if changed backend; then
      check "mypy" "$python" -m mypy backend
    fi
    check "Backend tests" "$python" -m pytest tests -q -x --disable-warnings \
      --ignore=tests/test_frontend_smoke.py --ignore=tests/test_mobile_web_smoke.py
  fi
fi

if changed mobile && [ -d mobile/node_modules ]; then
  check "Mobile typecheck" npm --prefix mobile run --silent typecheck
fi

if [ -n "$failures" ]; then
  printf '%s' "$failures" >&2
  exit 2
fi
