"""Lightweight prompt template renderer for pipeline step prompts.

Resolves ``{{key}}`` and ``{{key.sub}}`` references against *pipeline_data*
and *trigger* context so that rule authors can write prompts like::

    Is {{person_detections.0.name}} cooking on the stove?
    Based on the vision analysis: {{vision_response}} -- determine the activity.

Unresolvable references are left as-is so the LLM still sees the intent.
"""

from __future__ import annotations

import re
from typing import Any

# Matches {{ path.to.value }} with optional whitespace inside braces.
_VAR_RE = re.compile(r"\{\{\s*([\w][\w.]*)\s*\}\}")


def _resolve(path: str, data: dict) -> Any:
    """Walk *data* following a dotted path.

    Numeric segments are treated as list indices, e.g.
    ``person_detections.0.name`` resolves ``data["person_detections"][0]["name"]``.

    Returns *None* when any segment fails to resolve.
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
            # Try attribute access as last resort (e.g. dataclass fields)
            current = getattr(current, segment, None)
    return current


def render_template(template: str, pipeline_data: dict, trigger_vars: dict | None = None) -> str:
    """Replace ``{{key}}`` placeholders in *template* with values from *pipeline_data*.

    *trigger_vars* is an optional flat dict of trigger-level values (room_name,
    sensor_id, etc.) merged under a ``trigger`` namespace as well as top-level
    for convenience.

    Unresolvable placeholders are left unchanged so the LLM still sees them.
    """
    if "{{" not in template:
        return template

    merged: dict = dict(pipeline_data)
    if trigger_vars:
        merged["trigger"] = trigger_vars
        # Also promote trigger keys to top-level for convenience, but don't
        # overwrite existing pipeline_data keys.
        for k, v in trigger_vars.items():
            merged.setdefault(k, v)

    def _replace(match: re.Match) -> str:
        path = match.group(1)
        value = _resolve(path, merged)
        if value is None:
            return match.group(0)  # leave unresolved
        if isinstance(value, (dict, list)):
            import json
            return json.dumps(value)
        return str(value)

    return _VAR_RE.sub(_replace, template)
