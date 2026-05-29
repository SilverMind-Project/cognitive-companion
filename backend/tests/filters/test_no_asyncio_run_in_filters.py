"""WTR7: Static test — no asyncio.run() in filter or step files."""

from __future__ import annotations

import ast
from pathlib import Path


def _find_filter_and_step_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    dirs = [
        root / "filters",
        root / "steps",
    ]
    files: list[Path] = []
    for d in dirs:
        if d.exists():
            files.extend(d.rglob("*.py"))
    return files


def _has_asyncio_run(file_path: Path) -> bool:
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
        ):
            return True
    return False


def test_no_asyncio_run_in_filters_or_steps():
    """No production filter or step may use asyncio.run()."""
    violations: list[str] = []
    for f in _find_filter_and_step_files():
        if _has_asyncio_run(f):
            violations.append(str(f.relative_to(f.parents[2])))
    assert not violations, (
        "These files use asyncio.run() which is forbidden in filters/steps. "
        "Use async def evaluate() with await instead:\n" + "\n".join(violations)
    )
