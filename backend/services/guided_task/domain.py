"""Pure guided-task domain dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

TERMINAL_STATUSES = frozenset({"completed", "abandoned", "failed"})
LIVE_STATUSES = frozenset({"active", "waiting", "summoning", "escalated", "caregiver_takeover"})


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
