"""Shared helpers for pipeline step handlers.

Used by ``presence_query.py``, ``home_state.py``, and ``signal_emit.py`` for
person-resolution logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.steps.base import TriggerContext

logger = get_logger(__name__)


def make_trigger_vars(trigger: TriggerContext) -> dict[str, str]:
    """Build the standard ``trigger_vars`` dict for template rendering."""
    return {
        "room_name": trigger.room_name or "",
        "sensor_id": trigger.sensor_id or "",
    }


def resolve_person_id(
    config: dict,
    pipeline_data: dict,
    trigger_vars: Mapping[str, Any] | None = None,
) -> str | None:
    """Resolve a person_id from step config or upstream pipeline data.

    Resolution order:
    1. Explicit ``person_id`` in step config. ``{{template}}`` syntax is rendered here
       against ``pipeline_data`` (and ``trigger_vars``); nothing renders step config
       before a step runs. A template that does not resolve returns None: an author who
       named a person gets that person or nobody, never whoever comes first below.
    2. First entry from ``pipeline_data["persons"]`` (list of dicts with
       ``id`` or ``person_id`` keys).
    3. Scalar ``pipeline_data["person_id"]``.
    4. ``pipeline_data["trigger_event"]["person_id"]`` -- the fire_event()
       payload attached to an event-fired pipeline (e.g. a ``dementia_signal``
       rule), which carries no ``persons``/``person_id`` top-level key.

    Returns None when nothing is resolvable.
    """
    person_id = (config.get("person_id") or "").strip() or None
    if person_id and "{{" in person_id:
        rendered = render_template(person_id, pipeline_data, trigger_vars).strip()
        if not rendered or "{{" in rendered:
            # Field name only: the template and pipeline values may identify a person.
            logger.warning("person_id_template_unresolved", field="person_id")
            return None
        return rendered
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
