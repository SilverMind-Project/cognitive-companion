"""Guided-task caregiver takeover schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GuidedSessionSayIn(BaseModel):
    model_config = {"extra": "forbid"}

    text: str = Field(min_length=1, max_length=2000)


class GuidedSessionActionOut(BaseModel):
    status: str
    session_id: int


class GuidedSessionAdvanceOut(BaseModel):
    advanced: bool
    done: bool = False
    reason: str
    next_step: dict[str, Any] | None = None


class GuidedSessionTurnOut(BaseModel):
    actor: str
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] | None = None


class GuidedSessionEventOut(BaseModel):
    id: int
    at: datetime
    kind: str
    step_ord: int | None = None
    actor: str | None = None
    detail: dict[str, Any] | None = None


class GuidedSessionStepOut(BaseModel):
    ord: int
    prompt_text: str
    completion_gate: dict[str, Any]
    is_safety_critical: bool


class GuidedSessionOut(BaseModel):
    id: int
    routine_id: int
    person_id: str
    execution_id: int | None = None
    surface_id: str | None = None
    status: str
    current_step_ord: int
    attempts: int
    started_at: datetime
    last_activity_at: datetime
    completed_at: datetime | None = None
    outcome: str | None = None


class GuidedSessionDetailOut(BaseModel):
    session: GuidedSessionOut
    current_step: GuidedSessionStepOut | None = None
    recent_events: list[GuidedSessionEventOut]
    recent_transcript: list[GuidedSessionTurnOut]
