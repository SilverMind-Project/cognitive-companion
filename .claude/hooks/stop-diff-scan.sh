#!/usr/bin/env bash
# cognitive-companion: Stop hook: deterministic scan of the working-tree diff (EG-M06).
# Registered in .claude/settings.json; tested by .claude/hooks/tests/run.sh (make hooks-test).
# Each project carries its own copy of these hooks (program decision D1).
set -u
command -v jq >/dev/null 2>&1 || exit 0
payload=$(cat)
# Blocks the stop once with the findings; when stop_hook_active is set it reports nothing, so it
# can never loop. Grep-only and fast: it never runs tests.
active=$(printf '%s' "$payload" | jq -r '.stop_hook_active // false' 2>/dev/null)
[ "$active" = "true" ] && exit 0
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
EM=$(printf '\xe2\x80\x94')
modified=$(git diff --name-only HEAD 2>/dev/null)
untracked=$(git ls-files --others --exclude-standard 2>/dev/null)
problems=()

# Em-dashes on added lines of changed markdown, and anywhere in new markdown.
while IFS= read -r f; do
  case "$f" in *.md) ;; *) continue ;; esac
  if git diff -U0 HEAD -- "$f" 2>/dev/null | grep "^+" | grep -qF "$EM"; then problems+=("em-dash added in $f"); fi
done <<<"$modified"
while IFS= read -r f; do
  case "$f" in *.md) ;; *) continue ;; esac
  if [ -f "$f" ] && grep -qF "$EM" "$f"; then problems+=("em-dash in new file $f"); fi
done <<<"$untracked"

if grep -qx "backend/uv.lock" <<<"$modified" && ! grep -qx "backend/pyproject.toml" <<<"$modified"; then
  problems+=("backend/uv.lock changed but backend/pyproject.toml did not: revert the churn (git checkout backend/uv.lock) unless you re-locked on purpose")
fi
# A file whose only change is whitespace was usually reformatted by accident.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if git diff -w --quiet HEAD -- "$f" 2>/dev/null; then
    problems+=("$f has only whitespace changes (accidental formatting?)")
  fi
done <<<"$modified"

[ "${#problems[@]}" -gt 0 ] || exit 0
reason="Before finishing, fix or confirm: $(printf '%s; ' "${problems[@]}")"
jq -n --arg r "$reason" '{decision: "block", reason: $r}'
exit 0
