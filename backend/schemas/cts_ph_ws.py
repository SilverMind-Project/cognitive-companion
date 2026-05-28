"""WebSocket event payload schemas for the PH gateway.

Contract: WTR1 §1 — ``ph_id`` is the stable physical-track identifier.
These schemas define the wire format for cts_ph_update and
cts_ph_correction events broadcast over the shared WebSocket bus.
Consumers read ``event["type"]`` to dispatch.

Field names are stable — frontend composables depend on the exact names
``type``, ``current_identity_id``, ``ph_id``, and ``last_observed_at``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PHUpdateEvent(BaseModel):
    """Broadcast on WebSocket as ``cts_ph_update``."""

    type: str = Field(default="cts_ph_update", frozen=True)
    ph_id: str
    current_identity_id: str | None = None
    identity_committed: bool = False
    state: str = "active"
    posterior_top_label: str | None = None
    posterior_top_prob: float | None = None
    room_id: str | None = None
    last_observed_at: datetime | None = None


class PHCorrectionEvent(BaseModel):
    """Broadcast on WebSocket as ``cts_ph_correction``."""

    type: str = Field(default="cts_ph_correction", frozen=True)
    revision_id: str
    ph_id: str
    previous_identity_id: str | None = None
    new_identity_id: str | None = None
    actor: str = ""
    reason: str = ""
    kind: str = ""
    applied_at: datetime | None = None
