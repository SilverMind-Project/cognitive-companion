"""Lightweight prompt template renderer for pipeline step prompts.

Resolves ``{{key}}`` and ``{{key.sub}}`` references against *pipeline_data*
and *trigger* context so that rule authors can write prompts like::

    Is {{person_detections.0.name}} cooking on the stove?
    Based on the vision analysis: {{vision_response}}: determine the activity.
    The detected activity was: {{analysis_step.activity_type}}

Unresolvable references are left as-is so the LLM still sees the intent.

The resolver supports four traversal modes per path segment:

* dict keys (``foo.bar``)
* list / tuple indices (``items.0.name``)
* JSON string auto-parsing -- when a string value looks like a JSON object or
  array, it is transparently parsed so that downstream segments can traverse
  into it.  This allows ``{{my_llm_response.activity_type}}`` to work even
  when ``my_llm_response`` is stored as a raw JSON string rather than a dict.
* attribute access (``obj.field``) as a last resort for dataclasses & pydantic
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

__all__ = ["render_template", "resolve_path"]

# Matches {{ path.to.value }} with optional whitespace inside braces.
_VAR_RE = re.compile(r"\{\{\s*([\w][\w.]*)\s*\}\}")


def _try_parse_json(value: Any) -> Any:
    """If *value* is a JSON-encoded string, return the parsed object; otherwise return *value* unchanged."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped and stripped[0] in ("{", "["):
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            pass
    return value


def resolve_path(path: str, data: Mapping[str, Any] | Any) -> Any:
    """Walk *data* following a dotted *path*.

    Numeric segments are treated as list indices, e.g.
    ``person_detections.0.name`` resolves
    ``data["person_detections"][0]["name"]``.

    JSON string auto-parsing: when a segment resolves to a string that looks
    like a JSON object or array, it is automatically parsed before the next
    segment is applied.  This lets templates like
    ``{{llm_step_response.confidence}}`` work transparently whether the LLM
    response is stored as a dict or as a raw JSON string.

    Returns ``None`` when any segment fails to resolve (missing key,
    out-of-range index, or attribute not found).
    """
    current: Any = data
    segments = path.split(".")
    for i, segment in enumerate(segments):
        if current is None:
            return None
        # Auto-parse JSON strings before attempting further traversal
        if i > 0 and isinstance(current, str):
            current = _try_parse_json(current)
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            # Try attribute access as last resort (dataclass / pydantic field)
            current = getattr(current, segment, None)
    return current


def render_template(
    template: str,
    pipeline_data: Mapping[str, Any],
    trigger_vars: Mapping[str, Any] | None = None,
) -> str:
    """Replace ``{{key}}`` placeholders in *template* with values from *pipeline_data*.

    *trigger_vars* is an optional flat mapping of trigger-level values
    (room_name, sensor_id, etc.) merged under a ``trigger`` namespace as well
    as top-level for convenience (without overwriting ``pipeline_data`` keys).

    Unresolvable placeholders are left unchanged so the downstream LLM still
    sees the author's intent.
    """
    if "{{" not in template:
        return template

    merged: dict[str, Any] = dict(pipeline_data)
    if trigger_vars:
        merged["trigger"] = dict(trigger_vars)
        for k, v in trigger_vars.items():
            merged.setdefault(k, v)

    def _replace(match: re.Match[str]) -> str:
        path = match.group(1)
        value = resolve_path(path, merged)
        if value is None:
            return match.group(0)  # leave unresolved
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    return _VAR_RE.sub(_replace, template)
