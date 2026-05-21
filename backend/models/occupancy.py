"""Unified room occupancy state model.

One row per room, upserted whenever any source (CTS camera tracking,
HA presence sensor, or pipeline action) detects an occupancy change.
This is the single source of truth consumed by GET /api/v1/occupancy.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class RoomOccupancyState(Base):
    __tablename__ = "room_occupancy_state"

    room_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    occupied: Mapped[bool] = mapped_column(Boolean, default=False)
    # Timestamp when current occupancy window began; NULL when unoccupied.
    since: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # 'cts' | 'ha_sensor' | 'pipeline'
    source: Mapped[str] = mapped_column(String(32), default="unknown")
    # Person IDs currently in the room; empty list for ha_sensor (no identity).
    person_ids: Mapped[list] = mapped_column(JSON, default=list)
    last_updated: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )
