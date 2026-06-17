"""Companion surface registry models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime


class CompanionSurface(Base):
    """A tablet, speaker, or display that can host or summon guided tasks."""

    __tablename__ = "companion_surfaces"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    surface_type: Mapped[str] = mapped_column(String(16), nullable=False)
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id"), index=True, nullable=True
    )
    room_source: Mapped[str] = mapped_column(String(16), nullable=False, default="caregiver")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    room_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    room = relationship("Room")
