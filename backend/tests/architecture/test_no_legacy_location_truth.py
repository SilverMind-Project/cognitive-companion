"""R2: Architecture test -- filters and steps must NOT import legacy location tables.

After R2, any reference to PersonLocationState or PersonLocationHistory
in the filters/ or steps/ directories is a violation -- no exceptions
for transitional DEPRECATED markers, legacy fallbacks, or try-old-then-new.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Legacy tables that must not be read by product code.
_LEGACY_LOCATION_TABLES = (
    "PersonLocationState",
    "PersonLocationHistory",
)

# Directories to scan for product code.
_SCAN_DIRS = ("filters", "steps")


def _find_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    files: list[Path] = []
    for d in _SCAN_DIRS:
        target = root / d
        if target.exists():
            files.extend(target.rglob("*.py"))
    return files


def _references_legacy_location(file_path: Path) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return violations
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _LEGACY_LOCATION_TABLES:
            violations.append(f"  reference to '{node.id}' at line {node.lineno}")
        elif (
            isinstance(node, ast.Attribute)
            and hasattr(node, "attr")
            and node.attr in _LEGACY_LOCATION_TABLES
        ):
            violations.append(f"  reference to '.{node.attr}' at line {node.lineno}")
    return violations


def test_no_legacy_location_references_in_filters_or_steps():
    """R2: zero tolerance.  No file under filters/ or steps/ may reference
    PersonLocationState or PersonLocationHistory."""
    all_violations: list[str] = []
    for f in _find_files():
        v = _references_legacy_location(f)
        if not v:
            continue
        rel = str(f.relative_to(f.parents[2]))
        all_violations.append(f"{rel}:\n" + "\n".join(v))

    assert not all_violations, (
        "R2: Filters/steps reference legacy location tables. "
        "Remove all PersonLocationState/PersonLocationHistory references "
        "from filters/ and steps/. Use PersonLocationService instead:\n\n"
        + "\n\n".join(all_violations)
    )
