"""Pure guided-task domain dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

TERMINAL_STATUSES = frozenset({"completed", "abandoned", "failed"})
LIVE_STATUSES = frozenset({"active", "waiting", "summoning", "escalated", "caregiver_takeover"})
# Predicate for the one-live-session-per-person unique index:
# LIVE_STATUSES plus "pending", for a session state that precedes "active"/
# "summoning" but should still count as live. Keep in sync with the partial
# unique index predicate in models/guided_task.py and its migration.
UNIQUE_SESSION_STATUSES = LIVE_STATUSES | {"pending"}


class VisionConfirmConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    window_s: float | None = None
    max_frames: int | None = None
    min_confidence: float | None = None
    min_interval_s: float | None = None
    model_id: str | None = None
    max_disagreements: int | None = None
    on_max_disagreements: str | None = None


class VisionWatchConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool | None = None
    tick_s: int | None = None
    window_s: float | None = None
    max_frames: int | None = None
    model_id: str | None = None
    auto_advance: bool | None = None
    auto_advance_k: int | None = None


class VisionGateConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    gate_graph_rule_id: int | None = None
    confirm: VisionConfirmConfig | None = None
    watch: VisionWatchConfig | None = None


class CompletionGateConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vision: VisionGateConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict) and "vision_confirm" in data and "vision" not in data:
            data = dict(data)
            data["vision"] = data.pop("vision_confirm")
        return data


@dataclass(frozen=True)
class StepView:
    ord: int
    has_skip_condition: bool
    min_duration_s: int | None
    is_safety_critical: bool


@dataclass(frozen=True)
class SessionView:
    status: str
    current_step_ord: int
    attempts: int
    num_steps: int
    started_at: datetime
    last_activity_at: datetime
    step_entered_at: datetime


@dataclass(frozen=True)
class ResolvedPolicy:
    step_timeout_s: int
    max_step_attempts: int
    resume_grace_s: int


@dataclass(frozen=True)
class Decision:
    kind: str
    next_status: str
    next_step_ord: int
    attempts: int
    reason: str
    emergency: bool = False
