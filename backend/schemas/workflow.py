"""Pydantic schemas for workflow execution endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.schemas.common import OptionalUTCDatetime, UTCDatetime


class WorkflowExecutionOut(BaseModel):
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

    model_config = {"from_attributes": True}


class WorkflowExecutionListOut(BaseModel):
    """Lightweight version for list endpoints."""

    id: int
    rule_id: int
    rule_name: str | None = None
    status: str
    started_at: UTCDatetime
    completed_at: OptionalUTCDatetime = None
    updated_at: UTCDatetime

    model_config = {"from_attributes": True}
