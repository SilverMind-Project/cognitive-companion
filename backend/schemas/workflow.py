"""Pydantic schemas for workflow execution endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.schemas.common import OptionalUTCDatetime, OutSchema, UTCDatetime


class WorkflowExecutionOut(OutSchema):
    id: int
    rule_id: int
    rule_name: str | None = None
    event_log_id: int | None
    status: str
    current_step_id: int | None
    pipeline_data_json: dict[str, Any]
    started_at: UTCDatetime
    completed_at: OptionalUTCDatetime = None
    updated_at: UTCDatetime
    resume_at: OptionalUTCDatetime
    error: str | None


class WorkflowExecutionListOut(OutSchema):
    """Lightweight version for list endpoints."""

    id: int
    rule_id: int
    rule_name: str | None = None
    status: str
    started_at: UTCDatetime
    completed_at: OptionalUTCDatetime = None
    updated_at: UTCDatetime


# -- Execution Detail (rich view model) ---------------------------------------


class StepTimelineEntry(BaseModel):
    step_id: int | None = None
    label: str
    step_type: str
    icon: str
    category: str
    status: Literal["success", "failed", "skipped", "in_progress", "cancelled"]
    elapsed_seconds: float | None
    output_port: str = "main"
    resolved_config: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    cancellation_observed: bool = False


class ExecutionGraphStep(BaseModel):
    id: int
    label: str
    step_type: str
    position_x: float = 0.0
    position_y: float = 0.0
    output_ports: list[str] = Field(default_factory=lambda: ["main"])


class ExecutionGraphEdge(BaseModel):
    source_step_id: int
    source_port: str = "main"
    target_step_id: int
    target_port: str = "main"


class ExecutionGraph(BaseModel):
    steps: list[ExecutionGraphStep]
    edges: list[ExecutionGraphEdge]


class ExecutionDetailOut(BaseModel):
    id: int
    rule_id: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    rule_name: str
    trigger_type: str
    trigger_summary: str
    graph: ExecutionGraph | None = None
    timeline: list[StepTimelineEntry]
    cooloff_triggered: bool
    error: str | None = None
    can_cancel: bool
    can_rerun: bool


class ExecutionCancelledOut(BaseModel):
    """Acknowledgement of a cancel request."""

    id: int
    status: str


class ExecutionRerunOut(BaseModel):
    """Acknowledgement of a rerun; identifies the *new* execution, not the original."""

    execution_id: int
    rule_id: int
    status: str


class RerunRequest(BaseModel):
    from_step_label: str | None = None  # v2 feature; ignored in v1
