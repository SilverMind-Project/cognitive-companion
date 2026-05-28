"""WTR9: Architecture test — filters and steps must not import legacy location tables."""
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
        if isinstance(node, ast.Name):
            if node.id in _LEGACY_LOCATION_TABLES:
                violations.append(f"  reference to '{node.id}' at line {node.lineno}")
        elif isinstance(node, ast.Attribute):
            if hasattr(node, "attr") and node.attr in _LEGACY_LOCATION_TABLES:
                violations.append(f"  reference to '.{node.attr}' at line {node.lineno}")
    return violations


def test_filters_and_steps_use_person_location_service_primary():
    """Filters/steps that reference PersonLocationState/History must also
    use PersonLocationService as their primary path (WTR9 transitional)."""
    all_violations: list[str] = []
    for f in _find_files():
        v = _references_legacy_location(f)
        if not v:
            continue
        content = f.read_text()
        # Allow if the file also uses PersonLocationService as primary path.
        uses_pls = "person_location" in content and "services.person_location" in content
        uses_legacy_guard = "Legacy fallback" in content or "if db is not None" in content
        is_deprecated = "DEPRECATED (WTR9)" in content
        if uses_pls or uses_legacy_guard or is_deprecated:
            continue
        rel = str(f.relative_to(f.parents[2]))
        all_violations.append(f"{rel}:\n" + "\n".join(v))

    assert not all_violations, (
        "Filters/steps reference legacy location tables without PersonLocationService as primary. "
        "Use PersonLocationService instead:\n\n" + "\n\n".join(all_violations)
    )
