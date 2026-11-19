#!/usr/bin/env bash
# Verify that Python and Node runtime pins stay aligned across backend/pyproject.toml,
# backend/Dockerfile, frontend/.nvmrc, frontend/Dockerfile, and CI.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

check_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" != "$actual" ]; then
    echo "TOOLCHAIN DRIFT [$label]: expected '$expected', got '$actual'" >&2
    FAIL=1
  fi
}

# 1. Python major.minor alignment
PY_MINOR="$(grep -oE 'python_version = "[0-9]+\.[0-9]+"' "$ROOT/backend/pyproject.toml" | head -n1 | sed -E 's/.*"([^"]+)"/\1/')"
PY_COMPACT="py${PY_MINOR/./}"

RUFF_TARGET="$(grep -oE 'target-version = "py[0-9]+"' "$ROOT/backend/pyproject.toml" | head -n1 | sed -E 's/.*"([^"]+)"/\1/')"
check_eq "backend/pyproject.toml ruff target-version" "$PY_COMPACT" "$RUFF_TARGET"

DOCKER_PY="$(grep -oE 'FROM python:[0-9]+\.[0-9]+' "$ROOT/backend/Dockerfile" | head -n1 | cut -d: -f2)"
check_eq "backend/Dockerfile python" "$PY_MINOR" "$DOCKER_PY"

CI_PY="$(grep -oE 'uv python install [0-9]+\.[0-9]+' "$ROOT/.github/workflows/ci.yml" | head -n1 | awk '{print $NF}')"
check_eq ".github/workflows/ci.yml uv python install" "$PY_MINOR" "$CI_PY"

# 2. Node alignment between frontend/.nvmrc and frontend/Dockerfile
NODE_VER="$(tr -d '[:space:]' < "$ROOT/frontend/.nvmrc")"
DOCKER_NODE="$(grep -oE 'FROM node:[0-9]+\.[0-9]+\.[0-9]+' "$ROOT/frontend/Dockerfile" | head -n1 | cut -d: -f2)"
check_eq "frontend/Dockerfile node (vs frontend/.nvmrc)" "$NODE_VER" "$DOCKER_NODE"

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi
echo "Toolchain pins aligned (Python ${PY_MINOR}, Node ${NODE_VER})."
