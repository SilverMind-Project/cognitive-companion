"""Structural guard for the M29 guided-task service decomposition (G18).

Asserts every module the ``service.py`` decomposition produced stays under
the 500-line rule, the same guard style as hardening M08's field-carryover
test: a size regression should fail CI immediately rather than silently
regrowing a second 2000+ line monolith.

Scoped to the files this milestone's Target Shape table actually owns.
``gate_runner.py`` (585-609 lines) and ``metrics_service.py`` (664 lines)
already exceeded 500 lines before wave 3 began and were never part of G18
(which is specifically about ``service.py``'s growth); flagging them here
would misrepresent an out-of-scope pre-existing condition as a M29
regression. A future milestone can size-gate them if it chooses to take
them on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MAX_LINES = 500

_PACKAGE_DIR = Path(__file__).resolve().parents[3] / "services" / "guided_task"

_GUARDED_MODULES = [
    "service.py",
    "context.py",
    "routine_admin.py",
    "presentation.py",
    "retention.py",
    "runtime.py",
    "resident_actions.py",
    "summon.py",
    "watch.py",
    "caregiver.py",
    "completion/disagreement.py",
]


@pytest.mark.parametrize("relative_path", _GUARDED_MODULES)
def test_module_is_under_line_limit(relative_path: str) -> None:
    path = _PACKAGE_DIR / relative_path
    line_count = sum(1 for _ in path.open(encoding="utf-8"))
    assert line_count < MAX_LINES, (
        f"{relative_path} is {line_count} lines (limit {MAX_LINES}); "
        "split it before adding more code, per the M29 decomposition rule."
    )
