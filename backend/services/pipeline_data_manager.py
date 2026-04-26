"""Pipeline data lifecycle helpers.

Single source of truth for all mutations to ``pipeline_data`` dicts.
The executor and interactive-response service must use these helpers
instead of mutating the dict directly so that canonical per-step
namespacing is applied consistently and deep-copy semantics are enforced
for snapshots.

Canonical shape written by :func:`apply_step_result`
------------------------------------------------------
::

    {
        "trigger": {...},
        "system": {...},
        "_pipeline": {"started_at": "...", "completed_at": null},
        "_step_timings": [],
        "steps": {
            "llm_call_1": {
                "step_id": 12,
                "step_type": "llm_call",
                "outputs": {"llm_response": {...}}
            },
            "notification_1": {
                "step_id": 13,
                "step_type": "notification",
                "outputs": {"notification_dispatched": true}
            }
        }
    }

Template access
---------------
* ``{{steps.llm_call_1.outputs.llm_response.summary}}``
* ``{{steps.notification_1.outputs.notification_dispatched}}``

Pipeline control flags
----------------------
``_cooloff_triggered`` is a special flag that step handlers may include in
their ``result_data``.  When present, :func:`apply_step_result` promotes it
to the top level of *data* so the executor can read it without knowing which
step label to look under.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from backend.core.logging import get_logger
from backend.core.template import resolve_path

logger = get_logger(__name__)

_PIPELINE_CONTROL_FLAGS: frozenset[str] = frozenset({"_cooloff_triggered"})

# Keys that must never be used as step labels.
_RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "trigger",
        "system",
        "_pipeline",
        "_step_timings",
        "_cooloff_triggered",
        "_pending_interactive_step_id",
        "steps",
        "error",
    }
)


def reserved_pipeline_keys() -> frozenset[str]:
    """Return the set of keys that step labels must not collide with."""
    return _RESERVED_KEYS


def resolve_pipeline_value(
    data: Mapping[str, Any],
    path: str,
    default: Any = None,
) -> Any:
    """Resolve a dotted path against *data*, returning *default* on failure.

    Delegates to :func:`backend.core.template.resolve_path` so that all
    traversal semantics (list indices, JSON auto-parse, attribute fallback)
    are consistent with template rendering.
    """
    value = resolve_path(path, data)
    return value if value is not None else default


def build_initial_pipeline_data(
    trigger_type: str,
    sensor_id: str | None,
    room_name: str | None,
    media_paths: list[str],
    media_type: str,
    webhook_payload: dict | None,
    *,
    now_utc: datetime,
    now_local: datetime,
    timezone_name: str,
) -> dict[str, Any]:
    """Build the initial ``pipeline_data`` dict for a new execution."""
    data: dict[str, Any] = {
        "trigger": {
            "type": trigger_type,
            "sensor_id": sensor_id,
            "room_name": room_name,
            "media_paths": media_paths,
            "media_type": media_type,
        },
        "system": {
            "local_time": now_local.strftime("%I:%M %p"),
            "local_date": now_local.strftime("%Y-%m-%d"),
            "local_day_of_week": now_local.strftime("%A"),
            "timezone": timezone_name,
        },
        "_pipeline": {
            "started_at": now_utc.isoformat(),
            "completed_at": None,
        },
        "_step_timings": [],
        "steps": {},
    }
    if webhook_payload:
        data["trigger_input"] = webhook_payload
    return data


def apply_step_result(
    data: dict[str, Any],
    step_id: int,
    step_type: str,
    label: str,
    result_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge a step's output into *data* using the canonical namespace.

    Writes:
    * ``steps.<label>`` -- canonical entry keyed by step label
    * top-level pipeline control flags (``_cooloff_triggered``) when present

    Returns *data* (mutated in place) for convenience.
    """
    steps_ns: dict[str, Any] = data.setdefault("steps", {})

    steps_ns[label] = {
        "step_id": step_id,
        "step_type": step_type,
        "outputs": copy.deepcopy(result_data),
    }

    # Promote pipeline control flags to the top level so the executor can
    # read them without knowing which step label to look under.
    for flag in _PIPELINE_CONTROL_FLAGS:
        if flag in result_data:
            data[flag] = result_data[flag]
            logger.debug(
                "pipeline_control_flag_promoted",
                flag=flag,
                step_label=label,
                value=result_data[flag],
            )

    return data


def apply_interactive_response(
    data: dict[str, Any],
    step_id: int,
    step_type: str,
    label: str,
    output_key: str,
    response_payload: dict[str, Any],
    auto_escalate: bool,
    channel: str,
    action: str,
) -> dict[str, Any]:
    """Merge an interactive response into *data*.

    Writes the response under *output_key* and, when auto-escalation is
    configured, sets ``auto_escalate_triggered``.  Uses
    :func:`apply_step_result` so the canonical namespace is populated.

    Returns *data* (mutated in place).
    """
    result_data: dict[str, Any] = {output_key: response_payload}

    if auto_escalate and (action == "escalate" or channel == "timeout"):
        result_data["auto_escalate_triggered"] = True
        logger.info(
            "interactive_auto_escalate_triggered",
            step_id=step_id,
            reason="action_escalate" if action == "escalate" else "timeout",
        )

    apply_step_result(data, step_id, step_type, label, result_data)
    return data


def copy_pipeline_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *data* suitable for persisting to EventLog."""
    return copy.deepcopy(data)
