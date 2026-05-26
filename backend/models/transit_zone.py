"""Transit zone model for camera-blind room entry/exit detection (M2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class TransitZone(Base):
    __tablename__ = "transit_zones"

    id: Mapped[str] = mapped_column(UUID, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="door", server_default="door"
    )
    polygon: Mapped[dict] = mapped_column(JSONB, nullable=False)
    inside_room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id"), nullable=False
    )
    outside_room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id"), nullable=False
    )
    direction_vec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now(), nullable=False
    )
