"""Lightweight prompt template renderer for pipeline step prompts.

Resolves ``{{key}}`` and ``{{key.sub}}`` references against *pipeline_data*
and *trigger* context so that rule authors can write prompts like::

    Is {{person_detections.0.name}} cooking on the stove?
    Based on the vision analysis: {{vision_response}} — determine the activity.

Unresolvable references are left as-is so the LLM still sees the intent.

The resolver supports three traversal modes per path segment:

* dict keys (``foo.bar``)
* list / tuple indices (``items.0.name``)
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


def resolve_path(path: str, data: Mapping[str, Any] | Any) -> Any:
    """Walk *data* following a dotted *path*.

    Numeric segments are treated as list indices, e.g.
    ``person_detections.0.name`` resolves
    ``data["person_detections"][0]["name"]``.

    Returns ``None`` when any segment fails to resolve (missing key,
    out-of-range index, or attribute not found).
    """
    current: Any = data
    for segment in path.split("."):
        if current is None:
            return None
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
