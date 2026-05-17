from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from backend.core.database import Base
from backend.core.time import UTCDateTime


class HouseholdSettings(Base):
    """Singleton row (id=1) that stores household-level configuration."""

    __tablename__ = "household_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_household_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    floor_plan_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    floor_plan_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor_plan_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor_meters_per_pixel: Mapped[float | None] = mapped_column(Float, nullable=True)
    cts_adjacency_edges: Mapped[list | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )
