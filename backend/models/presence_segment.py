"""Presence segment ORM model (M4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class PresenceSegment(Base):
    __tablename__ = "presence_segments"

    id: Mapped[str] = mapped_column(UUID, primary_key=True)
    # household_members.id is String(64) and rooms.id is Integer per the
    # pre-existing schema (see alembic 0001_initial_schema).
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), nullable=False
    )
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id"), nullable=False
    )
    entered_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    exited_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    entry_source: Mapped[str] = mapped_column(String(32), nullable=False)
    exit_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    last_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(
        UUID, ForeignKey("presence_segments.id"), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
