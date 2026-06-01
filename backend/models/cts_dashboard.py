"""CTS dashboard support tables."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class CtsCameraOverlapGroup(Base):
    """Group of cameras that observe overlapping physical space."""

    __tablename__ = "cts_camera_overlap_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    camera_ids: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )


class CtsAlertSuppression(Base):
    """Caregiver suppression window for dementia-signal alerts."""

    __tablename__ = "cts_alert_suppressions"
    __table_args__ = (
        Index("ix_alert_suppressions_person_until", "person_id", "suppressed_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), nullable=False
    )
    signal_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suppressed_until: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
