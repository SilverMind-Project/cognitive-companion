"""Minimal guided-task caregiver notification escalator."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, RoutineStep
from backend.services.guided_task.store import GuidedTaskStore

logger = get_logger(__name__)


class NotifyOnlyEscalator:
    """Escalator implementation that records escalation and notifies caregivers."""

    def __init__(
        self,
        notification_dispatcher: Any,
        *,
        db_factory: Callable[[], Session],
        settings: Settings | None = None,
        conversation_manager: Any = None,
        time_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._dispatcher = notification_dispatcher
        self._store = GuidedTaskStore(db_factory)
        self._settings = settings or default_settings
        self._conversation_manager = conversation_manager
        self._time_fn = time_fn or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        now = self._time_fn()
        if now.tzinfo is None:
            raise ValueError("NotifyOnlyEscalator time_fn must return timezone-aware datetimes")
        return now

    async def escalate(self, *, session: GuidedSession, reason: str, emergency: bool) -> None:
        routine = self._store.get_routine(session.routine_id)
        if routine is None:
            raise NotFoundError("Routine", session.routine_id)
        steps = self._store.list_steps(session.routine_id)
        step = _current_step(steps, session.current_step_ord)

        now = self._now()
        updated = self._store.update_session(
            session.id,
            status="escalated",
        )
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        self._store.add_event(
            session_id=session.id,
            at=now,
            kind="escalation",
            step_ord=session.current_step_ord,
            actor="system",
            detail={"reason": reason, "emergency": emergency},
        )

        channels = list(
            routine.escalation_channels_override
            or self._settings.as_list("guided_task.escalation_channels")
        )
        if emergency and "ha_speaker_tts" not in channels:
            channels.append("ha_speaker_tts")

        message = self._message(
            routine_name=routine.name,
            step_text=step.prompt_template if step is not None else "",
            reason=reason,
            emergency=emergency,
        )
        dispatcher = self._dispatcher
        if dispatcher is None:
            logger.warning(
                "guided_escalation_skipped",
                session_id=session.id,
                reason="notification_dispatcher_unavailable",
            )
            return

        results = await dispatcher.dispatch(
            alert_level="emergency" if emergency else "warning",
            message=message,
            room_name="home",
            rule_config={"channels": channels},
        )
        logger.info(
            "guided_escalation_sent",
            session_id=session.id,
            reason=reason,
            emergency=emergency,
            channels=results,
        )

    def _message(
        self,
        *,
        routine_name: str,
        step_text: str,
        reason: str,
        emergency: bool,
    ) -> str:
        priority = "Emergency" if emergency else "Help requested"
        # TODO(M8): include recent transcript turns once guided sessions are
        # linked to realtime conversation sessions for caregiver takeover.
        return (
            f"{priority}: guided routine '{routine_name}' needs caregiver attention. "
            f"Reason: {reason}. Current instruction: {step_text}"
        )


def _current_step(steps: list[RoutineStep], ord_: int) -> RoutineStep | None:
    for step in steps:
        if step.ord == ord_:
            return step
    return None
