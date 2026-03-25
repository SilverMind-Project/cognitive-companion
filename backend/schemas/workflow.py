"""Pydantic schemas for workflow execution endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class WorkflowExecutionOut(BaseModel):
    id: int
    rule_id: int
    rule_name: str | None = None
    event_log_id: int | None
    status: str
    current_step_id: int | None
    pipeline_data_json: dict[str, Any]
    started_at: datetime
    updated_at: datetime
    resume_at: datetime | None
    error: str | None

    model_config = {"from_attributes": True}


class WorkflowExecutionListOut(BaseModel):
    """Lightweight version for list endpoints."""

    id: int
    rule_id: int
    rule_name: str | None = None
    status: str
    started_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
