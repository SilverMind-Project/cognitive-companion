"""Shared helpers for pipeline step handlers.

Used by ``presence_query.py`` and ``home_state.py`` for person-resolution logic.
"""

from __future__ import annotations


def resolve_person_id(config: dict, pipeline_data: dict) -> str | None:
    """Resolve a person_id from step config or upstream pipeline data.

    Resolution order:
    1. Explicit ``person_id`` in step config (supports ``{{template}}``
       syntax -- resolved by the template engine before this call).
    2. First entry from ``pipeline_data["persons"]`` (list of dicts with
       ``id`` or ``person_id`` keys).
    3. Scalar ``pipeline_data["person_id"]``.

    Returns None when nothing is resolvable.
    """
    person_id = (config.get("person_id") or "").strip() or None
    if person_id:
        return person_id

    persons = pipeline_data.get("persons")
    if isinstance(persons, list) and persons:
        first = persons[0]
        if isinstance(first, dict):
            return (first.get("id") or first.get("person_id") or None)

    candidate = pipeline_data.get("person_id")
    return candidate if isinstance(candidate, str) and candidate else None
