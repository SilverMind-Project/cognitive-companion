"""Pydantic schemas for workflow execution endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

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
    label: str
    step_type: str
    icon: str
    category: str
    status: Literal["success", "failed", "skipped", "in_progress", "cancelled"]
    elapsed_seconds: float | None
    resolved_config: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    logs: list[str] = []
    error: str | None = None
    cancellation_observed: bool = False


class ExecutionDetailOut(BaseModel):
    id: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    rule_name: str
    trigger_type: str
    trigger_summary: str
    timeline: list[StepTimelineEntry]
    cooloff_triggered: bool
    error: str | None = None
    can_cancel: bool
    can_rerun: bool


class RerunRequest(BaseModel):
    from_step_label: str | None = None  # v2 feature; ignored in v1
