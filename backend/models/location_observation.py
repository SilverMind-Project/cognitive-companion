"""Location observation ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class LocationObservation(Base):
    __tablename__ = "location_observations"
    # Composite PK because this is a TimescaleDB hypertable. household_members.id
    # is String(64) and rooms.id is Integer per the pre-existing schema.
    __table_args__ = (
        PrimaryKeyConstraint("id", "observed_at", name="location_observations_pkey"),
        Index("location_observations_observed_at_idx", text("observed_at DESC")),
        Index("idx_loc_obs_person", "person_id", text("observed_at DESC")),
        Index("idx_loc_obs_room", "room_id", text("observed_at DESC")),
    )

    id: Mapped[str] = mapped_column(UUID, nullable=False)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    floor_x_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_y_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    room_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rooms.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
