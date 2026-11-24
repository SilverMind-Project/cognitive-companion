"""WebSocket event schemas for guided-task caregiver consoles."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class GuidedEscalationEvent(BaseModel):
    type: Literal["guided_escalation"] = "guided_escalation"
    session_id: int
    routine_id: int
    person_id: str
    status: str
    reason: str
    emergency: bool
    urgent: bool
    takeover_url: str
    step_ord: int | None = None
    detail: dict[str, Any] | None = None
    at: datetime


class GuidedSessionUpdateEvent(BaseModel):
    type: Literal["guided_session_update"] = "guided_session_update"
    session_id: int
    routine_id: int
    person_id: str
    status: str
    current_step_ord: int
    event_kind: str
    actor: str | None = None
    detail: dict[str, Any] | None = None
    at: datetime


class GuidedSessionStateEvent(BaseModel):
    """Resident-safe guided-session state for the companion tablet (``/ws/audio``).

    Carries only what the resident's screen may show: no failure reasons,
    transcript, escalation detail, or takeover links. ``prompt_text`` is the
    step prompt rendered without the agent-only memory and preference context,
    and is empty when no step is in progress.
    """

    type: Literal["guided_session_state"] = "guided_session_state"
    session_id: int
    routine_id: int
    routine_name: str
    person_id: str
    status: str
    current_step_ord: int
    total_steps: int
    prompt_text: str
    at: datetime
