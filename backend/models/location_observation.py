"""Location observation ORM model (M4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class LocationObservation(Base):
    __tablename__ = "location_observations"

    id: Mapped[str] = mapped_column(UUID, primary_key=True)
    person_id: Mapped[str] = mapped_column(
        UUID, ForeignKey("household_members.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    floor_x_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_y_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    room_id: Mapped[str | None] = mapped_column(UUID, ForeignKey("rooms.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
