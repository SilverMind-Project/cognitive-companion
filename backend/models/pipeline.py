"""Composable pipeline step and workflow execution models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime

if TYPE_CHECKING:  # required: reciprocal SQLAlchemy relationship with rule.py
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
    except Exception:  # noqa: BLE001
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

    ``order`` remains a deterministic authoring and topology tiebreaker.
    Runtime sequencing follows ``PipelineEdge`` rows.
    """

    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    step_type: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(256), server_default="")
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position_x: Mapped[float] = mapped_column(default=0.0, server_default="0")
    position_y: Mapped[float] = mapped_column(default=0.0, server_default="0")

    rule: Mapped[Rule] = relationship(back_populates="steps")


class PipelineEdge(Base):
    """A directed edge between two pipeline steps."""

    __tablename__ = "pipeline_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), index=True)
    source_step_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_steps.id", ondelete="CASCADE")
    )
    source_port: Mapped[str] = mapped_column(String(64))
    target_step_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_steps.id", ondelete="CASCADE")
    )
    target_port: Mapped[str] = mapped_column(String(64), server_default="main")

    __table_args__ = (
        UniqueConstraint("source_step_id", "source_port", name="uq_edge_source_port"),
    )

    rule: Mapped[Rule] = relationship(back_populates="edges")
    source_step: Mapped[PipelineStep] = relationship(foreign_keys=[source_step_id])
    target_step: Mapped[PipelineStep] = relationship(foreign_keys=[target_step_id])


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
