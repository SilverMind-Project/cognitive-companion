"""Pydantic schemas for pipeline run endpoints and WebSocket events."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from backend.schemas.common import UTCDatetime


class DagNode(BaseModel):
    id: str
    label: str
    step_type: str
    status: Literal["pending", "running", "succeeded", "failed", "skipped", "cancelled", "waiting"]


class DagEdge(BaseModel):
    source: str
    source_handle: str = "main"
    target: str
    target_handle: str = "main"


class PipelineRunEnvelope(BaseModel):
    execution_id: int
    rule_id: int
    rule_name: str
    status: str
    started_at: UTCDatetime
    completed_at: UTCDatetime | None = None
    error: str | None = None
    nodes: list[DagNode]
    edges: list[DagEdge]


class PipelineExecutionEvent(BaseModel):
    """Typed event published on the /ws/pipeline channel."""

    type: str = "pipeline_event"
    event_type: Literal[
        "step_started",
        "step_completed",
        "pipeline_started",
        "pipeline_completed",
        "pipeline_failed",
        "pipeline_waiting",
        "pipeline_cancelled",
    ]
    execution_id: int
    rule_id: int
    rule_name: str
    step_id: str | None = None
    step_name: str | None = None
    step_type: str | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    output_port: str | None = None
    elapsed_ms: int | None = None
    sequence: int = 0


class IngestActivityEnvelope(BaseModel):
    """A single ingest activity event (frame received or rule triggered)."""

    id: str
    event_type: Literal["frame_received", "rule_triggered"]
    timestamp: UTCDatetime
    sensor_id: str | None = None
    trigger_type: str | None = None
    rule_name: str | None = None
