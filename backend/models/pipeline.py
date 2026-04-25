"""Composable pipeline step and workflow execution models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime

if TYPE_CHECKING:
    from backend.models.rule import Rule


def get_step_types() -> tuple[str, ...]:
    """Return all registered step type names.

    Uses the :class:`StepRegistry` at runtime; returns a default tuple
    if the registry has not been initialised yet (e.g., during migrations).
    """
    try:
        from backend.steps import StepRegistry

        names = StepRegistry.type_names()
        if names:
            return tuple(names)
    except Exception:
        pass
    # Fallback for DB migrations and early boot
    return (
        "person_identification",
        "notification",
        "ha_action",
        "activity_detection",
        "wait",
        "condition",
        "verification",
    )


# Backward-compatible alias
STEP_TYPES = get_step_types()


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

    rule: Mapped[Rule] = relationship(back_populates="steps")

    true_branch: Mapped[PipelineStep | None] = relationship(
        foreign_keys=[next_step_on_true], remote_side=[id], uselist=False
    )
    false_branch: Mapped[PipelineStep | None] = relationship(
        foreign_keys=[next_step_on_false], remote_side=[id], uselist=False
    )


class WorkflowExecution(Base):
    """Tracks a single run of a rule's pipeline, including paused/waiting state."""

    __tablename__ = "workflow_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), index=True)
    event_log_id: Mapped[int | None] = mapped_column(ForeignKey("event_logs.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="running", index=True
    )  # running, waiting, completed, failed, cancelled
    current_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_steps.id"), nullable=True
    )
    # MutableDict.as_mutable(JSON) is required: PipelineExecutor mutates this
    # dict in place across multiple commits, and plain JSON columns do not
    # track in-place mutations. Without it, writes from the second step
    # onwards silently drop on the floor while the row is marked "completed",
    # because the session factory runs with expire_on_commit=False.
    pipeline_data_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )
    resume_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": version}

    rule: Mapped[Rule] = relationship()
    current_step: Mapped[PipelineStep | None] = relationship(foreign_keys=[current_step_id])
