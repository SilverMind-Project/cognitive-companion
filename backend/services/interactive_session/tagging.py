from __future__ import annotations

from collections.abc import Callable
from typing import Any

_PREFIX_BUILDERS: dict[str, Callable[[int], str]] = {
    "quiz_start": lambda session_id: f"[quiz session {session_id}]",
}


def register_session_prefix(delivery_type: str, builder: Callable[[int], str]) -> None:
    """Register a prompt prefix for an interactive-session delivery type."""
    _PREFIX_BUILDERS[delivery_type] = builder


def prefix_for_delivery(metadata: dict[str, Any] | None) -> str:
    """Return the prompt prefix for delivery metadata, or an empty string."""
    if not metadata:
        return ""

    delivery_type = metadata.get("delivery_type", "")
    session_id = metadata.get("session_id")
    builder = _PREFIX_BUILDERS.get(delivery_type)
    if builder is None or session_id is None:
        return ""
    return builder(int(session_id))
