"""Sub-room functional zones in floor-meter coordinates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime


class RoomZone(Base):
    """A named sub-room polygon in floor-plane meters, never normalised image space."""

    __tablename__ = "room_zones"
    __table_args__ = (UniqueConstraint("room_id", "name", name="uq_room_zone_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(32), nullable=True)
    polygon: Mapped[list[list[float]]] = mapped_column(JSONB, nullable=False)
    camera_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    room = relationship("Room")
