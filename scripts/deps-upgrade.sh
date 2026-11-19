#!/usr/bin/env bash
# Check or perform coordinated dependency upgrades across backend (uv.lock) and
# frontend (package-lock.json), preserving internal git pins and running all gates.
#
# Usage:
#   scripts/deps-upgrade.sh --check   Read-only list of outdated Python and npm packages
#   scripts/deps-upgrade.sh --apply   Upgrade PyPI uv.lock (preserving git pins) + safe npm updates, then verify

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:---check}"
NODE_VER="$(tr -d '[:space:]' < "$ROOT/frontend/.nvmrc")"

run_frontend() {
  bash -lc "set -e; NVM_SH=\"\${NVM_DIR:-$HOME/.nvm}/nvm.sh\"; . \"\$NVM_SH\"; nvm use ${NODE_VER} >/dev/null; cd \"$ROOT/frontend\"; $1"
}

case "$MODE" in
  --check)
    echo "=== Outdated Python packages (backend) ==="
    (cd "$ROOT" && uv pip list --python backend/.venv/bin/python --outdated || true)
    echo "=== Outdated npm packages (frontend) ==="
    run_frontend "npm outdated || true"
    ;;

  --apply)
    echo "=== 1. Upgrading PyPI packages in backend/uv.lock (preserving internal git pins) ==="
    (
      cd "$ROOT/backend"
      mapfile -t PYPI_ARGS < <(
        uv run --frozen python - <<'PY'
import tomllib
from pathlib import Path

lock = tomllib.loads(Path("uv.lock").read_text(encoding="utf-8"))
for pkg in lock.get("package", []):
    src = pkg.get("source", {})
    if isinstance(src, dict) and "registry" in src:
        print(f"--upgrade-package={pkg['name']}")
PY
      )
      uv lock "${PYPI_ARGS[@]}"
      uv sync --frozen --extra dev
    )

    echo "=== 2. Refreshing frontend lockfile within declared semver ranges ==="
    run_frontend "npm update"

    echo "=== 3. Running toolchain check, contracts, full quality gate, audit, and deptry ==="
    (cd "$ROOT" && make check-toolchain contracts && run_frontend "npm run generate:api" && make check-all audit deps-check)
    ;;

  *)
    echo "usage: $0 [--check|--apply]" >&2
    exit 64
    ;;
esac
