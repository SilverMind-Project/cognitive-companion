"""Shared helpers for pipeline step handlers.

Used by ``presence_query.py``, ``home_state.py``, and ``signal_emit.py`` for
person-resolution logic.
"""

from __future__ import annotations

from backend.steps.base import TriggerContext


def make_trigger_vars(trigger: TriggerContext) -> dict[str, str]:
    """Build the standard ``trigger_vars`` dict for template rendering."""
    return {
        "room_name": trigger.room_name or "",
        "sensor_id": trigger.sensor_id or "",
    }


def resolve_person_id(config: dict, pipeline_data: dict) -> str | None:
    """Resolve a person_id from step config or upstream pipeline data.

    Resolution order:
    1. Explicit ``person_id`` in step config (supports ``{{template}}``
       syntax -- resolved by the template engine before this call).
    2. First entry from ``pipeline_data["persons"]`` (list of dicts with
       ``id`` or ``person_id`` keys).
    3. Scalar ``pipeline_data["person_id"]``.
    4. ``pipeline_data["trigger_event"]["person_id"]`` -- the fire_event()
       payload attached to an event-fired pipeline (e.g. a ``dementia_signal``
       rule), which carries no ``persons``/``person_id`` top-level key.

    Returns None when nothing is resolvable.
    """
    person_id = (config.get("person_id") or "").strip() or None
    if person_id:
        return person_id

    persons = pipeline_data.get("persons")
    if isinstance(persons, list) and persons:
        first = persons[0]
        if isinstance(first, dict):
            return first.get("id") or first.get("person_id") or None

    candidate = pipeline_data.get("person_id")
    if isinstance(candidate, str) and candidate:
        return candidate

    trigger_event = pipeline_data.get("trigger_event")
    if isinstance(trigger_event, dict):
        event_person_id = trigger_event.get("person_id")
        if isinstance(event_person_id, str) and event_person_id:
            return event_person_id

    return None
