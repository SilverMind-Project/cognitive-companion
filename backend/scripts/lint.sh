#!/usr/bin/env bash
# Run all linters and type checkers.
# Usage:  ./scripts/lint.sh          (check only)
#         ./scripts/lint.sh --fix    (auto-fix what ruff can)
set -euo pipefail

cd "$(dirname "$0")/.."   # backend/

FIX_FLAG=""
if [[ "${1:-}" == "--fix" ]]; then
    FIX_FLAG="--fix"
fi

echo "=== ruff check ==="
uv run ruff check . $FIX_FLAG

echo ""
echo "=== ruff format check ==="
uv run ruff format --check .

echo ""
echo "=== mypy ==="
cd ..  # repo root  mypy needs to resolve 'backend' as a package
backend/.venv/bin/mypy backend/ --config-file backend/pyproject.toml

echo ""
echo "All checks passed."
