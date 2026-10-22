#!/usr/bin/env bash
# cognitive-companion: PostToolUse feedback after Edit and Write (EG-M06).
# Registered in .claude/settings.json; tested by .claude/hooks/tests/run.sh (make hooks-test).
# Each project carries its own copy of these hooks (program decision D1).
set -u
command -v jq >/dev/null 2>&1 || exit 0
payload=$(cat)
file=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$file" ] && [ -f "$file" ] || exit 0
root=${CLAUDE_PROJECT_DIR:-$(pwd)}
rel=${file#"$root"/}
EM=$(printf '\xe2\x80\x94')

# A failed check returns decision=block: the reason reaches Claude as feedback. Never edits files.
block() {
  jq -n --arg r "$1" '{decision: "block", reason: $r}'
  exit 0
}

case "$rel" in
  *.md)
    lines=$(grep -nF "$EM" "$file" | cut -d: -f1 | head -5 | paste -sd, -)
    [ -z "$lines" ] || block "em-dash in $rel (lines $lines); replace it with a colon, comma, semicolon, or parentheses."
    ;;
  backend/*.py)
    out=$("$root/backend/.venv/bin/ruff" check --quiet "$file" 2>&1) || block "ruff check $rel failed:
$(printf '%s' "$out" | head -20)"
    ;;
  frontend/src/*.js|frontend/src/*.ts|frontend/src/*.vue)
    if command -v node >/dev/null 2>&1 && [ -x "$root/frontend/node_modules/.bin/eslint" ]; then
      out=$(cd "$root/frontend" && node_modules/.bin/eslint --max-warnings 0 "$file" 2>&1) || block "eslint $rel failed:
$(printf '%s' "$out" | head -20)"
    fi
    ;;
esac
exit 0
