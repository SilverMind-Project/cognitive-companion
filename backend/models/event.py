"""Event log model for tracking pipeline executions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id"), nullable=True)
    rule_name: Mapped[str | None] = mapped_column(String(256), index=True)
    sensor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    room_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trigger_type: Mapped[str] = mapped_column(
        String(32)
    )  # sensor_event, cron, sensor_poll, manual
    media_paths_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pipeline_data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), index=True
    )  # processing, completed, ignored, failed
    workflow_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_executions.id"), nullable=True
    )
