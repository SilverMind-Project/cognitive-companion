"""Rule definitions with composable pipeline steps."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime

if TYPE_CHECKING:
    from backend.models.pipeline import PipelineStep


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Trigger configuration
    trigger_type: Mapped[str] = mapped_column(
        String(32), default="sensor_event"
    )  # sensor_event, cron, manual, webhook, occupancy_duration, telegram
    schedule_cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_sensor_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )  # for periodic rules that need to capture from a specific sensor

    # Webhook trigger configuration
    webhook_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Occupancy duration trigger configuration: {"min_minutes": int}
    occupancy_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Telegram command trigger configuration:
    #   {"command": "/medication", "allowed_chat_ids": ["123456"], "respond_with_ack": true}
    telegram_trigger_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Rate limiting
    cool_off_minutes: Mapped[int] = mapped_column(Integer, default=5)
    max_daily_triggers: Mapped[int] = mapped_column(Integer, default=3)

    # Concurrency & execution limits
    # 0 = unlimited concurrent executions; default 1 (at most one running at a time)
    max_concurrent_executions: Mapped[int] = mapped_column(Integer, default=1)
    # 0 = no timeout; default 5 minutes
    execution_timeout_minutes: Mapped[int] = mapped_column(Integer, default=5)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), onupdate=func.now(), nullable=True
    )

    # Relationships
    steps: Mapped[list[PipelineStep]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        order_by="PipelineStep.order",
    )
    contexts: Mapped[list[RuleContext]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list[RuleDependency]] = relationship(
        back_populates="dependent_rule",
        foreign_keys="RuleDependency.dependent_rule_id",
        cascade="all, delete-orphan",
    )


class RuleContext(Base):
    """Context filter for a rule. Multiple contexts of the same type are ORed;
    different types are ANDed.

    Supported context_types:
      - time_range: {"start_time": "HH:MM", "end_time": "HH:MM"}
      - room: {"room_id": 1} or {"room_name": "Kitchen"}
      - day_of_week: {"days": [0,1,2,3,4]}  (Mon=0..Sun=6)
      - person_presence: {"person_id": "grandma", "room_name": "Kitchen"}
      - person_activity: {"person_id": "grandma", "activity_type": "eating",
                          "within_minutes": 30}
    """

    __tablename__ = "rule_contexts"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    context_type: Mapped[str] = mapped_column(String(32))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    negate: Mapped[bool] = mapped_column(Boolean, default=False)

    rule: Mapped[Rule] = relationship(back_populates="contexts")


class RuleDependency(Base):
    """Parent rule must have succeeded within lookback_minutes for this rule to fire."""

    __tablename__ = "rule_dependencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    dependent_rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    parent_rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    lookback_minutes: Mapped[int] = mapped_column(Integer, default=30)
    require_success: Mapped[bool] = mapped_column(Boolean, default=True)

    dependent_rule: Mapped[Rule] = relationship(foreign_keys=[dependent_rule_id])
    parent_rule: Mapped[Rule] = relationship(foreign_keys=[parent_rule_id])
