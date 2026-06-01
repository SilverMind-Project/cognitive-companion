"""WebSocket event schemas for pipeline execution."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StepNodeRef(BaseModel):
    id: str
    label: str
    step_type: str
    enabled: bool


class EdgeRef(BaseModel):
    source: str
    source_handle: str
    target: str
    target_handle: str = "main"


class PipelineEventBase(BaseModel):
    type: str = "pipeline_event"
    event_type: str
    execution_id: int
    rule_id: int
    rule_name: str
    status: str
    sequence: int


class PipelineStartedEvent(PipelineEventBase):
    event_type: Literal["pipeline_started"] = "pipeline_started"
    started_at: datetime
    steps: list[StepNodeRef] = Field(default_factory=list)
    edges: list[EdgeRef] = Field(default_factory=list)


class StepStartedEvent(PipelineEventBase):
    event_type: Literal["step_started"] = "step_started"
    step_id: str
    step_name: str
    step_type: str
    started_at: datetime


class StepCompletedEvent(PipelineEventBase):
    event_type: Literal["step_completed"] = "step_completed"
    step_id: str
    step_name: str
    step_type: str
    started_at: datetime | None = None
    finished_at: datetime
    error_code: str | None = None
    output_port: str = "main"
    elapsed_ms: int | None = None


class PipelineWaitingEvent(PipelineEventBase):
    event_type: Literal["pipeline_waiting"] = "pipeline_waiting"


class PipelineCompletedEvent(PipelineEventBase):
    event_type: Literal["pipeline_completed"] = "pipeline_completed"
    finished_at: datetime


class PipelineFailedEvent(PipelineEventBase):
    event_type: Literal["pipeline_failed"] = "pipeline_failed"
    error_code: str
    finished_at: datetime


class PipelineCancelledEvent(PipelineEventBase):
    event_type: Literal["pipeline_cancelled"] = "pipeline_cancelled"
    finished_at: datetime | None = None
