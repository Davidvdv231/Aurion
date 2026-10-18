#!/bin/bash
# Runs the backend test suite when Claude finishes a turn with uncommitted
# changes under backend/ or tests/, and sends failures back to Claude.
# The Playwright smoke tests are left to CI and to running them by hand.
set -euo pipefail

# If this hook already sent Claude back once, let it stop instead of looping.
if python3 -c 'import json, sys; sys.exit(0 if json.load(sys.stdin).get("stop_hook_active") else 1)'; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
changes="$(git status --porcelain -- backend tests 2>/dev/null)" || exit 0
[ -n "$changes" ] || exit 0

if [ -x .venv/bin/python ]; then
  python=.venv/bin/python
else
  python=python3
fi
"$python" -c "import fastapi, pytest" 2>/dev/null || exit 0

if ! output="$("$python" -m pytest tests -q -x --disable-warnings \
  --ignore=tests/test_frontend_smoke.py --ignore=tests/test_mobile_web_smoke.py 2>&1)"; then
  echo "Backend tests failed:" >&2
  echo "$output" | tail -n 40 >&2
  exit 2
fi
