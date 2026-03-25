from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class EmergencyAlert(Base):
    __tablename__ = "emergency_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    alert_type: Mapped[str] = mapped_column(String(64))  # bathroom_time_exceeded, loud_noise, fall_detected
    description: Mapped[str] = mapped_column(Text)
    sensor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    room_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    assistance_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Tracks which channels were notified: {"telegram": true, "tts": true, ...}
    notification_sent_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
