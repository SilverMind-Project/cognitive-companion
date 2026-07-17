#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to a committed frontend artifact.

The backend is the single source of truth for the browser/backend contract. This script writes
`frontend/openapi.json`, from which `npm run generate:api` generates the TypeScript types the
API client is keyed on (M17). Output is deterministic (`sort_keys=True`, `indent=2`, trailing
newline) so `make openapi` followed by `git diff --exit-code` is a clean CI drift gate, the
same pattern as `export_vocabularies.py`.

`backend.main` imports without a database -- `app.openapi()` needs route definitions only, not
the lifespan -- so the real app is used directly rather than a routes-only reconstruction.

Run via ``uv run --project backend python backend/scripts/export_openapi.py``.
Pass ``--check`` to verify the committed artifact is current without writing (used by CI and
by the determinism test).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "frontend" / "openapi.json"

# Allow running as `python backend/scripts/export_openapi.py` (adds the script's own
# directory to sys.path, not the repo root) as well as `-m` / pytest-style invocation.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_spec() -> dict:
    """Return the app's OpenAPI schema.

    Imported inside the function so the module-level `sys.path` fix is applied first.
    """
    from backend.main import app

    return app.openapi()


def render(spec: dict) -> str:
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed artifact differs from the current schema",
    )
    args = parser.parse_args()

    text = render(build_spec())
    rel = OUTPUT_PATH.relative_to(REPO_ROOT)

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"{rel} is missing; run `make openapi`", file=sys.stderr)
            return 1
        if OUTPUT_PATH.read_text() != text:
            print(
                f"{rel} is stale; run `make openapi` and commit the result",
                file=sys.stderr,
            )
            return 1
        print(f"{rel} is up to date", file=sys.stderr)
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(text)
    print(f"Wrote {rel}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
