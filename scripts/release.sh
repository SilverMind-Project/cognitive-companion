#!/usr/bin/env bash
# Cut a release: bump backend/_version.py, commit, and tag. The file is the only place the version
# lives (backend/pyproject.toml reads it), so a commit that is not a release changes nothing.
#
# Usage: scripts/release.sh patch|minor|major
#        scripts/release.sh --self-test
#
# It does not push: review the commit, then run `git push --follow-tags origin main`.

set -euo pipefail

VERSION_FILE="backend/_version.py"

# Prints the next version; `next_version 0.7.148 minor` is 0.8.0.
next_version() {
  local major minor patch
  IFS='.' read -r major minor patch <<< "$1"
  case "$2" in
    patch) echo "${major}.${minor}.$((patch + 1))" ;;
    minor) echo "${major}.$((minor + 1)).0" ;;
    major) echo "$((major + 1)).0.0" ;;
    *) echo "release: part must be patch, minor, or major (got '$2')" >&2; return 1 ;;
  esac
}

self_test() {
  local got
  for case in "0.7.148 patch 0.7.149" "0.7.148 minor 0.8.0" "0.7.148 major 1.0.0"; do
    read -r from part want <<< "$case"
    got=$(next_version "$from" "$part")
    [[ "$got" == "$want" ]] || { echo "release self-test: $from $part gave $got" >&2; exit 1; }
  done
  if next_version 0.7.148 bogus 2>/dev/null; then
    echo "release self-test: an unknown part was accepted" >&2
    exit 1
  fi
  echo "release self-test passed"
}

if [[ "${1:-}" == "--self-test" ]]; then
  self_test
  exit 0
fi

part="${1:-}"
[[ "$(git symbolic-ref --short HEAD)" == "main" ]] || { echo "release: not on main" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "release: the working tree is not clean" >&2; exit 1; }

current=$(grep -oP '(?<=__version__ = ")[^"]+' "$VERSION_FILE")
new=$(next_version "$current" "$part")
tag="v${new}"
if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
  echo "release: tag ${tag} already exists" >&2
  exit 1
fi

printf '__version__ = "%s"\n' "$new" > "$VERSION_FILE"
git add "$VERSION_FILE"
git commit -q -m "Release ${new}"
git tag -a "$tag" -m "Release ${new}"
echo "Released ${new}. Review it, then run: git push --follow-tags origin main"
