"""Regression fence for C5: every ServiceContainer field must have a consumer.

A field with zero consumers under ``backend/steps/`` or ``backend/filters/``
is either genuinely dead (delete it) or consumed only via ``app.state``
directly, bypassing the container entirely (also delete it from the
container -- ``rag_service``, ``ha_state_cache``, and ``person_id_client``
were all removed for exactly this reason). This test would have caught all
three at introduction time.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from backend.steps.base import ServiceContainer

_SEARCH_DIRS = ("backend/steps", "backend/filters")
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _consumer_exists(field: str) -> bool:
    needles = (f"services.{field}", f"services and services.{field}")
    for rel_dir in _SEARCH_DIRS:
        base = _REPO_ROOT / rel_dir
        for path in base.rglob("*.py"):
            text = path.read_text()
            if any(needle in text for needle in needles):
                return True
    return False


def test_every_container_field_has_a_consumer():
    fields = [f.name for f in dataclasses.fields(ServiceContainer) if f.name != "db_factory"]
    unconsumed = [field for field in fields if not _consumer_exists(field)]
    assert not unconsumed, (
        f"ServiceContainer fields with no consumer in steps/ or filters/: {unconsumed}. "
        "Either wire a consumer or delete the field (see C5)."
    )
