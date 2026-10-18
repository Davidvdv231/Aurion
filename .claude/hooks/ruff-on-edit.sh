#!/bin/bash
# Formats and lints a Python file under backend/ or tests/ (the paths CI checks)
# after Claude edits it. Lint errors ruff can't fix are sent back to Claude.
set -euo pipefail

file="$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')"
case "$file" in
  "$CLAUDE_PROJECT_DIR"/backend/*.py | "$CLAUDE_PROJECT_DIR"/tests/*.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

# Prefer the venv's ruff: it's the version pinned in requirements-dev.lock.
if [ -x "$CLAUDE_PROJECT_DIR/.venv/bin/ruff" ]; then
  ruff="$CLAUDE_PROJECT_DIR/.venv/bin/ruff"
elif command -v ruff >/dev/null; then
  ruff=ruff
else
  exit 0
fi

# Fix before formatting: removing an unused import can leave blank lines that
# only the formatter cleans up. Then report whatever is still wrong.
"$ruff" check --fix --quiet "$file" >/dev/null 2>&1 || true
"$ruff" format --quiet "$file" 2>/dev/null || true
if ! output="$("$ruff" check --quiet "$file" 2>&1)"; then
  echo "$output" >&2
  exit 2
fi
