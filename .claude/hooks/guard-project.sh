#!/usr/bin/env bash
# cognitive-companion: PreToolUse guard for Bash commands (EG-M06).
# Registered in .claude/settings.json; tested by .claude/hooks/tests/run.sh (make hooks-test).
# Each project carries its own copy of these hooks (program decision D1).
set -u
command -v jq >/dev/null 2>&1 || exit 0
payload=$(cat)
raw=$(printf '%s' "$payload" | jq -er '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -n "$raw" ] || exit 0

# Drop heredoc bodies (file writes via cat, tee, python): their text is data, not commands.
cmd=$(printf '%s\n' "$raw" | awk '
  skipping { if ($0 == term) { skipping = 0 }; next }
  {
    print
    if (match($0, /<<-?[ \t]*["\047]?[A-Za-z_][A-Za-z0-9_]*["\047]?/)) {
      t = substr($0, RSTART, RLENGTH); sub(/^<<-?[ \t]*/, "", t); gsub(/["\047]/, "", t)
      term = t; skipping = 1
    }
  }')
# Quoted strings are arguments (printf text, grep patterns, commit messages), not commands.
bare=$(printf '%s\n' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
# A program in command position: line start or after a separator, past env assignments and
# wrappers such as timeout. RUNS_PYTEST is true when a segment invokes pytest.
CMDPOS='(?:^|[;&|(]|&&|\|\|)\s*(?:(?:timeout\s+\S+|env|nice|time|[A-Za-z_][A-Za-z0-9_]*=\S+)\s+)*'

deny() {
  echo "Blocked by .claude/hooks/guard-project.sh (cognitive-companion): $1 Run it yourself with ! if it is intended." >&2
  exit 2
}

# Whole-tree ruff format (writes): formats hundreds of untouched files. --check/--diff only read.
if printf '%s' "$bare" | grep -qP '\bruff\s+format\b(?:\s+-[-\w]+(?:=\S+)?)*\s*(?:(?:\./)?backend/?|\./?)?\s*(?:$|[;&|)])' \
   && ! printf '%s' "$bare" | grep -qP '\bruff\s+format\b[^;&|]*\s--(check|diff)\b'; then
  deny "ruff format over the whole backend; format only the files you touched."
fi
# Test runs outside the project venv: bare pytest or a bare python -m pytest in command position.
if printf '%s' "$bare" | grep -qP "${CMDPOS}(pytest|python3?(\.\d+)?\s+-m\s+pytest)(?=\$|[\s;&|)])" \
   && ! printf '%s' "$bare" | grep -qP '\.venv/bin/activate\b'; then
  deny "pytest outside the project venv; use backend/.venv/bin/python -m pytest, uv run --project backend pytest, or make."
fi
# uv flags that rewrite uv.lock.
if printf '%s' "$bare" | grep -qP '\buv\s+(run|sync)\b[^;&|]*\s--(no-frozen|upgrade|upgrade-package)\b'; then
  deny "uv run/sync with --no-frozen or --upgrade rewrites backend/uv.lock; re-lock deliberately with uv lock."
fi

exit 0
