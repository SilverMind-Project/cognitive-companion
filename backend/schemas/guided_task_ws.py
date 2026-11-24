"""Guided-task WebSocket schemas: caregiver console events, the resident-safe
tablet state, and the tablet's guided-step taps."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictInt


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


class ResidentGuidedStateOut(BaseModel):
    """What the companion tablet shows on load or reconnect: the session with a
    step in progress, or ``None`` (which clears a widget left over from a
    session that ended while the tablet was away)."""

    session: GuidedSessionStateEvent | None = None


class GuidedStepActionIn(BaseModel):
    """A tap on the resident's guided-task widget, sent over ``/ws/audio``.

    ``step_ord`` is the step her screen showed. It is required to complete a
    step, so a tap on a screen that has not caught up never completes a step
    she has not seen.
    """

    model_config = ConfigDict(extra="ignore")

    type: Literal["guided_step_action"] = "guided_step_action"
    session_id: StrictInt
    action: Literal["done", "repeat", "help"]
    step_ord: StrictInt | None = None


class GuidedStepActionResultEvent(BaseModel):
    """The tapping tablet's own acknowledgement, so its buttons never stay busy.

    ``reason`` is a code for the screen's logic (for example
    ``stale_step_completion``), never text to show her.
    """

    type: Literal["guided_step_action_result"] = "guided_step_action_result"
    session_id: int
    action: str
    accepted: bool
    reason: str | None = None
