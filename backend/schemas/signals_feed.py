"""Unified signals-feed envelope.

One caregiver-facing event, regardless of source: a CTS dementia signal
(``cts_signals``) or a pipeline rule that fired a notification (``event_logs``).
Both shapes are normalised to this envelope so the Dashboard, the Alerts page,
and MCP all read one feed with a ``source`` provenance tag.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SignalSource = Literal["cts", "pipeline_rule"]


class SignalEnvelope(BaseModel):
    """One unified signal/alert row."""

    id: str = Field(description="Stable per-source id: 'cts:<row_id>' or 'rule:<event_log_id>'.")
    source: SignalSource
    kind: str = Field(description="signal_type for CTS, rule_name for pipeline rules.")
    severity: str = Field(description="info | warning | emergency | reminder")
    room_id: int | None = None
    room_name: str | None = None
    person_id: str | None = None
    display_name: str | None = None
    created_at: datetime | None = None
    resolved: bool = False
    detail: str = Field(default="", description="Human-readable summary of the event.")

    # Mutation capability differs by source: CTS rows can be acknowledged or
    # deleted; pipeline-rule rows are read-only in the feed.
    can_acknowledge: bool = False
    can_delete: bool = False

    def to_mcp(self) -> dict[str, Any]:
        """Flat dict for MCP tool return (parity with the router shape)."""
        return {
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "severity": self.severity,
            "room_id": self.room_id,
            "room_name": self.room_name,
            "person_id": self.person_id,
            "display_name": self.display_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved": self.resolved,
            "detail": self.detail,
        }


# Ordering helper: most severe first within the same instant is rarely needed,
# but the feed sorts by recency primarily; severity rank is exposed for the UI.
SEVERITY_RANK: dict[str, int] = {"emergency": 3, "warning": 2, "info": 1, "reminder": 0}
