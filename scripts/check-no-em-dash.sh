#!/usr/bin/env bash
# Fail when markdown contains an em-dash (U+2014). Markdown in this repository never uses one:
# use a colon, comma, semicolon, or parentheses. (EG-M07; identical copy in each repository.)
#
#   scripts/check-no-em-dash.sh              every tracked *.md file
#   scripts/check-no-em-dash.sh FILE...      only the given files (non-markdown is ignored)
#   scripts/check-no-em-dash.sh --self-test  prove the check still fails on an em-dash (CI canary)
#
# A line that must quote one verbatim (for example program output in a code block) may carry
# the marker <!-- em-dash-ok -->; reviewers should expect zero such markers.
set -euo pipefail

# Path prefixes never checked (vendored or generated trees).
NO_EM_DASH_EXCLUDE=(
  "node_modules/"
  "tools/go-mod-cache/"
)

EM=$(printf '\xe2\x80\x94')

if [ "${1:-}" = "--self-test" ]; then
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  printf 'bad %s dash\n' "$EM" >"$tmp/bad.md"
  printf 'quoted %s output <!-- em-dash-ok -->\n' "$EM" >"$tmp/marked.md"
  printf 'clean: colon, comma; parentheses\n' >"$tmp/clean.md"
  "$0" "$tmp/bad.md" >/dev/null 2>&1 && { echo "self-test: an em-dash was not detected" >&2; exit 1; }
  "$0" "$tmp/marked.md" "$tmp/clean.md" || { echo "self-test: a clean or marked file failed" >&2; exit 1; }
  echo "check-no-em-dash self-test passed"
  exit 0
fi

cd "$(git rev-parse --show-toplevel)"

if [ "$#" -gt 0 ]; then
  files=("$@")
else
  mapfile -t files < <(git ls-files '*.md')
fi

status=0
for f in "${files[@]}"; do
  case "$f" in *.md) ;; *) continue ;; esac
  [ -f "$f" ] || continue
  skip=0
  for prefix in "${NO_EM_DASH_EXCLUDE[@]}"; do
    case "$f" in "$prefix"*) skip=1 ;; esac
  done
  [ "$skip" = 0 ] || continue
  if hits=$(grep -nF "$EM" "$f" | grep -vF '<!-- em-dash-ok -->'); then
    while IFS= read -r hit; do
      echo "$f:${hit%%:*}: em-dash; use a colon, comma, semicolon, or parentheses"
    done <<<"$hits"
    status=1
  fi
done
exit "$status"
