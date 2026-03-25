"""Composable pipeline step and workflow execution models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


STEP_TYPES = (
    "person_identification",
    "vision_analysis",
    "logic_reasoning",
    "translation",
    "notification",
    "ha_action",
    "activity_detection",
    "wait",
    "condition",
    "verification",
)


class PipelineStep(Base):
    """A single step in a rule's composable pipeline.

    Steps are executed in ``order`` sequence. Condition steps may override
    the next step via ``next_step_on_true`` / ``next_step_on_false``.
    """

    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    step_type: Mapped[str] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Branching: only used by condition steps
    next_step_on_true: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_steps.id"), nullable=True
    )
    next_step_on_false: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_steps.id"), nullable=True
    )

    rule: Mapped["Rule"] = relationship(back_populates="steps")  # noqa: F821

    true_branch: Mapped["PipelineStep | None"] = relationship(
        foreign_keys=[next_step_on_true], remote_side=[id], uselist=False
    )
    false_branch: Mapped["PipelineStep | None"] = relationship(
        foreign_keys=[next_step_on_false], remote_side=[id], uselist=False
    )


class WorkflowExecution(Base):
    """Tracks a single run of a rule's pipeline, including paused/waiting state."""

    __tablename__ = "workflow_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), index=True)
    event_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_logs.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="running", index=True
    )  # running, waiting, completed, failed, cancelled
    current_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_steps.id"), nullable=True
    )
    pipeline_data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resume_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    rule: Mapped["Rule"] = relationship()  # noqa: F821
    current_step: Mapped["PipelineStep | None"] = relationship(
        foreign_keys=[current_step_id]
    )
