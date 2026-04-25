"""Pipeline data lifecycle helpers.

Single source of truth for all mutations to ``pipeline_data`` dicts.
The executor and interactive-response service must use these helpers
instead of mutating the dict directly so that:

* canonical per-step namespacing is applied consistently
* legacy top-level aliases are projected for backward compatibility
* alias collisions are detected and logged
* deep-copy semantics are enforced for snapshots

Canonical shape written by :func:`apply_step_result`
------------------------------------------------------
::

    {
        "trigger": {...},
        "system": {...},
        "_pipeline": {"started_at": "...", "completed_at": null},
        "_step_timings": [],
        "steps": {
            "by_id": {
                "12": {
                    "step_id": 12,
                    "step_type": "llm_call",
                    "label": "Vision Step",
                    "label_slug": "vision_step",
                    "outputs": {"vision_response": {...}}
                }
            },
            "by_label": {"vision_step": "12"},
            "sequence": ["12"]
        },
        # legacy top-level aliases (last-writer-wins, collision logged)
        "vision_response": {...},
        "_alias_collisions": [{"key": "...", "old_step_id": ..., "new_step_id": ...}]
    }

Template access
---------------
* Canonical: ``{{steps.by_id.12.outputs.vision_response.summary}}``
* By label:  ``{{steps.by_label.vision_step}}`` resolves to ``"12"``; then
  ``{{steps.by_id.12.outputs.vision_response.summary}}``
* Legacy (deprecated): ``{{vision_response.summary}}``
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from backend.core.logging import get_logger
from backend.core.template import resolve_path

logger = get_logger(__name__)

# Keys that must never be overwritten by a step label slug.
_RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "trigger",
        "system",
        "_pipeline",
        "_step_timings",
        "_cooloff_triggered",
        "_alias_collisions",
        "_pending_interactive_step_id",
        "steps",
        "error",
    }
)

_SLUG_RE = re.compile(r"[^a-z0-9_]")


def reserved_pipeline_keys() -> frozenset[str]:
    """Return the set of keys that step label slugs must not overwrite."""
    return _RESERVED_KEYS


def slugify_step_label(label: str | None) -> str | None:
    """Normalise a step label into a safe identifier slug.

    Returns ``None`` when the label is empty or produces an empty slug.
    """
    if not label:
        return None
    slug = label.strip().lower()
    slug = _SLUG_RE.sub("_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or None


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
    """Build the initial ``pipeline_data`` dict for a new execution.

    This is the canonical factory; the executor must not construct the dict
    inline.
    """
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
        "steps": {
            "by_id": {},
            "by_label": {},
            "sequence": [],
        },
    }
    if webhook_payload:
        data["trigger_input"] = webhook_payload
    return data


def apply_step_result(
    data: dict[str, Any],
    step_id: int,
    step_type: str,
    label: str | None,
    result_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge a step's output into *data* using the canonical namespace.

    Writes:
    * ``steps.by_id.<step_id>.outputs`` -- canonical, always present
    * ``steps.by_label.<slug>`` -- friendly alias pointing to step_id str
    * ``steps.sequence`` -- ordered list of step_id strings
    * legacy top-level aliases -- last-writer-wins, collision logged

    Returns *data* (mutated in place) for convenience.
    """
    step_id_str = str(step_id)
    slug = slugify_step_label(label)

    # Ensure the steps namespace exists (may be absent on resumed executions
    # that pre-date this helper).
    steps_ns: dict[str, Any] = data.setdefault("steps", {"by_id": {}, "by_label": {}, "sequence": []})
    by_id: dict[str, Any] = steps_ns.setdefault("by_id", {})
    by_label: dict[str, Any] = steps_ns.setdefault("by_label", {})
    sequence: list[str] = steps_ns.setdefault("sequence", [])

    # Deep-copy the outputs so mutations to pipeline_data don't corrupt the
    # canonical record.
    outputs = copy.deepcopy(result_data)

    by_id[step_id_str] = {
        "step_id": step_id,
        "step_type": step_type,
        "label": label,
        "label_slug": slug,
        "outputs": outputs,
    }

    if step_id_str not in sequence:
        sequence.append(step_id_str)

    # Friendly label alias
    if slug and slug not in _RESERVED_KEYS:
        existing_id = by_label.get(slug)
        if existing_id is not None and existing_id != step_id_str:
            logger.warning(
                "pipeline_label_alias_collision",
                slug=slug,
                old_step_id=existing_id,
                new_step_id=step_id_str,
            )
        by_label[slug] = step_id_str

    # Legacy top-level aliases (last-writer-wins)
    collisions: list[dict[str, Any]] = data.setdefault("_alias_collisions", [])
    for key, value in result_data.items():
        if key in _RESERVED_KEYS:
            continue
        existing = data.get(key)
        if existing is not None:
            # Find which step previously wrote this key
            old_step_id: str | None = None
            for sid, entry in by_id.items():
                if sid != step_id_str and key in entry.get("outputs", {}):
                    old_step_id = sid
                    break
            if old_step_id is not None:
                logger.warning(
                    "pipeline_alias_collision",
                    key=key,
                    old_step_id=old_step_id,
                    new_step_id=step_id_str,
                )
                collisions.append(
                    {
                        "key": key,
                        "old_step_id": old_step_id,
                        "new_step_id": step_id_str,
                    }
                )
        data[key] = value

    return data


def apply_interactive_response(
    data: dict[str, Any],
    step_id: int,
    step_type: str,
    label: str | None,
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
    """Return a deep copy of *data* suitable for persisting to EventLog.

    Using ``dict(data)`` (shallow copy) is unsafe because nested structures
    (e.g. ``_pipeline``, ``steps``) would be shared references.
    """
    return copy.deepcopy(data)
