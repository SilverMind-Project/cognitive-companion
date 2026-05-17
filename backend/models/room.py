from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime

if TYPE_CHECKING:  # required: reciprocal SQLAlchemy relationship with sensor.py
    from backend.models.sensor import Sensor


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    ha_area_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    floor_polygon: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())

    sensors: Mapped[list[Sensor]] = relationship(back_populates="room")
