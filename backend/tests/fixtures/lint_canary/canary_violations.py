"""Deliberate ruff violations for backend/tests/architecture/test_lint_canary.py.

Excluded from normal lint runs via backend/pyproject.toml. Intentionally omits
``from __future__ import annotations`` (I002) and triggers each guarded ruff rule.
"""

import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)  # TID251


def canary_violations(table: str) -> None:
    naive = datetime.datetime(2026, 1, 1, 12, 0)  # DTZ001
    x: int = "bad"  # type: ignore  # PGH003
    logger.info(f"table={table} naive={naive} x={x}")  # G004
    _sql = f"SELECT * FROM {table}"  # S608
    # unused_var = 42  # ERA001
    try:
        int(table)
    except ValueError:
        logger.error("failed", exc_info=True)  # G201
    try:
        int(table)
    except Exception:  # BLE001
        return


async def canary_async_blocking(path: str) -> tuple[bytes, bytes]:
    with open(path, "rb") as fh:  # ASYNC230
        a = fh.read()
    b = Path(path).read_bytes()  # ASYNC240
    return a, b
