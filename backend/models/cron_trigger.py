"""Cron trigger model -- decoupled from rules for many-to-many scheduling."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.rule import Rule


class CronTrigger(Base, TimestampMixin):
    __tablename__ = "cron_triggers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    expression: Mapped[str] = mapped_column(String(128))  # "30 9 * * 1-5"
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    rules: Mapped[list[Rule]] = relationship(
        secondary="rule_cron_triggers",
        back_populates="cron_triggers",
    )


class RuleCronTrigger(Base):
    __tablename__ = "rule_cron_triggers"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), nullable=False)
    cron_trigger_id: Mapped[int] = mapped_column(ForeignKey("cron_triggers.id"), nullable=False)
