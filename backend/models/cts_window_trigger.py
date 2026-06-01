"""CtsWindowTrigger model — sliding-window trigger for CTS frame aggregation.

A ``CtsWindowTrigger`` fires a ``cts_window`` pipeline event when a
per-camera sliding window meets configured detection and identity
thresholds. Each trigger can be linked to one or more rules via the
``rule_cts_window_triggers`` join table.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base, TimestampMixin
from backend.core.time import UTCDateTime

if TYPE_CHECKING:
    from backend.models.rule import Rule


class CtsWindowTrigger(Base, TimestampMixin):
    """Sliding-window CTS trigger configuration."""

    __tablename__ = "cts_window_triggers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(_uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    window_seconds: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    min_detections: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_identities: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cameras: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    rooms: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    cooldown_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rules: Mapped[list[Rule]] = relationship(
        secondary="rule_cts_window_triggers",
        back_populates="cts_window_triggers",
    )


class RuleCtsWindowTrigger(Base):
    """Many-to-many join table linking rules to CTS window triggers."""

    __tablename__ = "rule_cts_window_triggers"
    __table_args__ = (
        Index("ix_rule_cts_window_triggers_rule_id", "rule_id"),
        Index("ix_rule_cts_window_triggers_ct_id", "cts_window_trigger_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), nullable=False)
    cts_window_trigger_id: Mapped[str] = mapped_column(
        ForeignKey("cts_window_triggers.id", ondelete="CASCADE"), nullable=False
    )
