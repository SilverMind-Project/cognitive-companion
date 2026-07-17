"""Response envelope for the unified room-occupancy read-model.

One record per occupied room, carrying identified ``person_ids`` plus an
``unknown_count`` for hypotheses that have no identity yet. Every record
carries a ``source`` provenance tag (``world_tracker`` | ``ha_sensor`` |
``pipeline``). The frontend renders these fields; it never invents them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RoomOccupancyStateEnvelope(BaseModel):
    """Live occupancy of one room from the unified read-model."""

    room_id: int | None = Field(
        default=None, description="rooms.id, when the source resolves a room id."
    )
    room_name: str
    occupied: bool
    person_ids: list[str] = Field(
        default_factory=list, description="Identified household member ids in the room."
    )
    unknown_count: int = Field(
        default=0, ge=0, description="Unidentified hypotheses currently in the room."
    )
    source: str = Field(description="world_tracker | ha_sensor | pipeline")
    since: datetime | None = Field(
        default=None, description="When the current occupancy window began."
    )
    last_updated: datetime | None = Field(
        default=None, description="Timestamp of the most recent observation."
    )

    def to_mcp(self) -> dict:
        """Flat dict for MCP tool return (parity with the router shape)."""
        return {
            "room_id": self.room_id,
            "room_name": self.room_name,
            "occupied": self.occupied,
            "person_ids": list(self.person_ids),
            "unknown_count": self.unknown_count,
            "source": self.source,
            "since": self.since.isoformat() if self.since else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class OccupancyResponse(BaseModel):
    """Live occupancy for every occupied room, keyed by room name."""

    occupancy: dict[str, RoomOccupancyStateEnvelope] = Field(default_factory=dict)


class OccupancyHistoryResponse(BaseModel):
    """Smoothed occupancy time-series for one room.

    ``room`` and ``hours`` are optional because the endpoint drops them when the sensor-polling
    service is unavailable, returning a bare ``{"history": []}``. Modelled as-is; tightening
    that branch is a behavioral change, not a typing one.
    """

    room: str | None = None
    hours: float | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
