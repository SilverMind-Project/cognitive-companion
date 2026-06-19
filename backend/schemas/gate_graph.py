"""Schemas for the gate-graph CRUD + preset + test-run endpoints (VG08)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from backend.schemas.pipeline_types import PipelineEdgeOut
from backend.schemas.rule import PipelineStepOut, RuleListOut, RuleOut


class GateGraphListEnvelope(BaseModel):
    items: list[RuleListOut]
    total: int


class GateGraphCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str
    description: str | None = None
    from_preset: str | None = None


class GateGraphDetail(BaseModel):
    rule: RuleOut
    steps: list[PipelineStepOut]
    edges: list[PipelineEdgeOut]


class GateValidateResult(BaseModel):
    valid: bool
    errors: list[str]
    template_errors: dict[str, list[dict]] = {}


class GateTestRunRequest(BaseModel):
    model_config = {"extra": "forbid"}

    person_id: str | None = None
    room_name: str | None = None
    sensor_id: str | None = None
    profile: Literal["confirm", "watch"] = "confirm"
    camera_ids: list[str] | None = None
    zone_id: int | None = None


class GateVerdictOut(BaseModel):
    complete: bool
    confidence: float
    reason: str
    node_results: dict[str, Any] = {}
    cost: dict[str, Any] = {}
    profile: str


class GatePresetOut(BaseModel):
    key: str
    name: str
    description: str
    summary: str
