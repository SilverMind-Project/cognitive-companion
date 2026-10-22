#!/usr/bin/env bash
# Test table for this project's Claude Code hooks (EG-M06). Run: make hooks-test
# Feeds hook payloads to each script and checks exit codes and decisions. Hermetic: the stop-hook
# cases run in a throwaway git repository; the lint case writes one temporary file and removes it.
set -u
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HOOKS/../.." && pwd)"
pass=0; fail=0
ok()  { pass=$((pass+1)); }
bad() { fail=$((fail+1)); echo "FAIL: $1"; }
EM=$(printf '\xe2\x80\x94')
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

guard() {  # guard <allow|deny> <command>
  local expected=$1 cmd=$2 got=allow
  jq -n --arg c "$cmd" '{tool_name: "Bash", tool_input: {command: $c}}' \
    | CLAUDE_PROJECT_DIR="$ROOT" bash "$HOOKS/guard-project.sh" >/dev/null 2>&1
  [ $? = 2 ] && got=deny
  [ "$got" = "$expected" ] && ok || bad "guard expected $expected, got $got: $cmd"
}

post_edit() {  # post_edit <block|pass> <file>
  local expected=$1 file=$2 out got=pass
  out=$(jq -n --arg f "$file" '{tool_name: "Edit", tool_input: {file_path: $f}}' \
    | CLAUDE_PROJECT_DIR="$ROOT" bash "$HOOKS/post-edit.sh" 2>/dev/null)
  printf '%s' "$out" | jq -e '.decision == "block"' >/dev/null 2>&1 && got=block
  [ "$got" = "$expected" ] && ok || bad "post-edit expected $expected, got $got: $file"
}

stop() {  # stop <block|pass> <repo> [stop_hook_active]
  local expected=$1 repo=$2 active=${3:-false} out got=pass
  out=$(jq -n --argjson a "$active" '{stop_hook_active: $a}' \
    | CLAUDE_PROJECT_DIR="$repo" bash "$HOOKS/stop-diff-scan.sh" 2>/dev/null)
  printf '%s' "$out" | jq -e '.decision == "block"' >/dev/null 2>&1 && got=block
  [ "$got" = "$expected" ] && ok || bad "stop expected $expected, got $got (repo $repo, active $active)"
}

LOCK="backend/uv.lock"; MANIFEST="backend/pyproject.toml"

new_repo() {  # new_repo <dir>: a committed repo with the files the stop checks look at
  mkdir -p "$1" && cd "$1" || return 1
  git init -q && git config user.email t@example.invalid && git config user.name t
  mkdir -p "$(dirname "$LOCK")"
  printf 'a\n' >README.md; printf 'lock\n' >"$LOCK"; printf 'm\n' >"$MANIFEST"; printf 'x = 1\n' >code.py
  git add -A && git commit -qm init
  cd - >/dev/null || return 1
}

# --- guard-project -------------------------------------------------------------------------
guard deny  'backend/.venv/bin/ruff format backend'
guard deny  'cd backend && .venv/bin/ruff format .'
guard deny  'backend/.venv/bin/ruff format'
guard deny  'uv run --project backend ruff format backend/ && echo done'
guard allow 'backend/.venv/bin/ruff format backend/mcp/middleware.py backend/core/auth.py'
guard allow 'backend/.venv/bin/ruff format --check backend/tests/mcp/test_x.py'
guard allow 'backend/.venv/bin/ruff check backend'
guard deny  'pytest backend/tests/core'
guard deny  'python3 -m pytest backend/tests'
guard allow 'backend/.venv/bin/python -m pytest backend/tests/core -q'
guard allow 'backend/.venv/bin/pytest backend/tests/core'
guard allow 'uv run --project backend pytest backend/tests/core'
guard allow 'make check-all'
guard allow 'printf "%s\\n" "run pytest and ruff format backend later" >> notes.txt'
guard allow 'make -n check-all | grep pytest'
guard allow 'grep -nE "^(check|test|pytest)[a-z-]*:" Makefile'
guard allow 'cd backend && .venv/bin/ruff format --check .'
guard deny  'timeout 600 pytest backend/tests'
guard deny  'echo start; pytest -q'
guard allow 'grep -n integration backend/pyproject.toml pytest.ini'
guard allow 'source backend/.venv/bin/activate && python -m pytest backend/tests/core'
guard deny  'uv sync --upgrade --project backend'
guard deny  'uv run --no-frozen --project backend pytest'
guard allow 'uv lock --project backend'
guard allow 'git status --short'
guard allow $'cat > notes.md <<\'EOF\'\nruff format backend\nEOF'

# --- stop-diff-scan ------------------------------------------------------------------------
r="$TMP/clean"; new_repo "$r"
stop pass "$r"
r="$TMP/emdash"; new_repo "$r"; printf 'b %s c\n' "$EM" >>"$r/README.md"
stop block "$r"
stop pass "$r" true                       # stop_hook_active: never loops
r="$TMP/newmd"; new_repo "$r"; printf 'x %s y\n' "$EM" >"$r/NEW.md"
stop block "$r"
r="$TMP/plainmd"; new_repo "$r"; printf 'plain addition\n' >>"$r/README.md"
stop pass "$r"
r="$TMP/lock"; new_repo "$r"; printf 'churn\n' >>"$r/$LOCK"
stop block "$r"
r="$TMP/relock"; new_repo "$r"; printf 'churn\n' >>"$r/$LOCK"; printf 'dep\n' >>"$r/$MANIFEST"
stop pass "$r"
r="$TMP/ws"; new_repo "$r"; printf 'x  =  1\n' >"$r/code.py"
stop block "$r"
r="$TMP/realedit"; new_repo "$r"; printf 'x = 2\n' >"$r/code.py"
stop pass "$r"

# --- post-edit: Python lint (temporary file inside backend/, removed on exit) ---------------
lintfile="$ROOT/backend/_hooktest_tmp_$$.py"; trap 'rm -rf "$TMP" "$lintfile"' EXIT
printf 'from __future__ import annotations\n\nimport os\n' >"$lintfile"
post_edit block "$lintfile"
printf 'from __future__ import annotations\n\nVALUE = 1\n' >"$lintfile"
post_edit pass "$lintfile"
rm -f "$lintfile"

# --- post-edit: markdown -------------------------------------------------------------------
printf 'fine: colon, comma; parentheses\n' >"$TMP/clean.md"
post_edit pass "$TMP/clean.md"
printf 'bad %s dash\n' "$EM" >"$TMP/dash.md"
post_edit block "$TMP/dash.md"
post_edit pass "$TMP/does-not-exist.md"

# --- session-context ----------------------------------------------------------------------
lines=$(CLAUDE_PROJECT_DIR="$ROOT" bash "$HOOKS/session-context.sh" | wc -l)
if [ "$lines" -ge 1 ] && [ "$lines" -le 10 ]; then ok; else bad "session-context printed $lines lines (want 1-10)"; fi

# --- malformed payloads fail open ---------------------------------------------------------
for h in "$HOOKS"/*.sh; do
  [ "$(basename "$h")" = session-context.sh ] && continue
  printf 'not json' | CLAUDE_PROJECT_DIR="$ROOT" bash "$h" >/dev/null 2>&1
  [ $? = 0 ] && ok || bad "$(basename "$h") does not fail open on a malformed payload"
done

echo "hooks: $pass passed, $fail failed"
[ "$fail" = 0 ]
