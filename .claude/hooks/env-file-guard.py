#!/usr/bin/env python3
"""Refuses shell commands that name a real .env file.

The Read deny rules in .claude/settings.json keep Claude's file tools out of
.env files; this covers the shell (`cat .env`, `source .env.production`,
`open('.env')` in a `python -c` string). Templates such as .env.example stay
allowed. It's a guard against accidental reads, not a boundary: a command that
never spells out the file name (a glob like `.en*`, `grep -r`) isn't caught.
"""

import json
import re
import shlex
import sys

TEMPLATES = {".env.example", ".env.sample", ".env.template"}
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1")  # not a <<< here-string
# A .env path inside a quoted string, e.g. open('.env') or Path("config/.env").
QUOTED_PATH = re.compile(r"""(['"])(?:[^'"\s]*/)?(\.env(?:\.[\w.-]+)?)\1""")


def strip_heredocs(command: str) -> str:
    """Drops heredoc bodies, which are text (often commit messages), not paths."""
    kept, delimiters = [], []
    for line in command.split("\n"):
        if delimiters:
            if line.strip() == delimiters[0]:
                delimiters.pop(0)
            continue
        kept.append(line)
        delimiters.extend(match.group(2) for match in HEREDOC.finditer(line))
    return "\n".join(kept)


def names_env_file(name: str) -> bool:
    name = name.rstrip("/").rsplit("/", 1)[-1]
    if not name.startswith(".env") or name in TEMPLATES:
        return False
    # ".env", ".env.local", or a glob such as ".env*"; not ".envrc".
    return len(name) == 4 or name[4] in ".*?["


def tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    words = []
    for word in lexer:
        # VAR=.env and --file=.env name the file after the "=".
        words.extend(word.split("="))
    return words


def main() -> int:
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    command = strip_heredocs(command)
    try:
        words = tokens(command)
    except ValueError:  # unbalanced quotes: check whitespace-separated words instead
        words = command.split()
    found = [word for word in words if names_env_file(word)]
    found += [m.group(2) for m in QUOTED_PATH.finditer(command) if names_env_file(m.group(2))]
    if not found:
        return 0
    print(
        f"Blocked: this command names {found[0]}, which may hold real secrets. "
        "Don't read, copy, edit or delete .env files from the shell; if the task "
        "needs one, ask the user to do it. .env.example is fine to use.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
