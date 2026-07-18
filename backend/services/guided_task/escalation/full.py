"""Full guided-task escalation ladder and caregiver takeover notification."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, RoutineStep
from backend.schemas.guided_task_ws import GuidedEscalationEvent
from backend.services.guided_task.store import GuidedTaskStore

logger = get_logger(__name__)


class FullEscalator:
    """Escalator implementation with caregiver context, WS events, and emergencies."""

    def __init__(
        self,
        notification_dispatcher: Any,
        *,
        db_factory: Callable[[], Session],
        ws_manager: Any = None,
        admin_ws_broadcaster: Any = None,
        conversation_manager: Any = None,
        settings: Settings | None = None,
    ) -> None:
        self._dispatcher = notification_dispatcher
        self._store = GuidedTaskStore(db_factory)
        self._ws_manager = ws_manager
        self._admin_ws_broadcaster = admin_ws_broadcaster
        self._conversation_manager = conversation_manager
        self._settings = settings or default_settings

    async def escalate(self, *, session: GuidedSession, reason: str, emergency: bool) -> None:
        routine = self._store.get_routine(session.routine_id)
        if routine is None:
            raise NotFoundError("Routine", session.routine_id)
        steps = self._store.list_steps(session.routine_id)
        step = _current_step(steps, session.current_step_ord)

        updated = self._store.update_session(
            session.id,
            status="escalated",
            last_activity_at=session.last_activity_at,
        )
        if updated is None:
            raise NotFoundError("Guided session", session.id)

        detail = {
            "reason": reason,
            "emergency": emergency,
            "takeover_url": self._takeover_url(session.id),
        }
        self._store.add_event(
            session_id=session.id,
            at=session.last_activity_at,
            kind="escalation",
            step_ord=session.current_step_ord,
            actor="system",
            detail=detail,
        )

        channels = self._channels(routine.escalation_channels_override, emergency=emergency)
        message = self._message(
            routine_name=routine.name,
            step_text=step.prompt_template if step is not None else "",
            reason=reason,
            emergency=emergency,
            takeover_url=self._takeover_url(session.id),
            transcript=self._recent_transcript(session.conversation_session_id),
        )

        await self._broadcast_escalation(updated, reason=reason, emergency=emergency, detail=detail)

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
            rule_config={"channels": channels, "urgent": emergency},
        )
        logger.info(
            "guided_emergency_alert" if emergency else "guided_escalation_sent",
            session_id=session.id,
            reason=reason,
            emergency=emergency,
            channels=results,
        )

    def _channels(self, override: list[str] | None, *, emergency: bool) -> list[str]:
        channels = list(override or self._settings.as_list("guided_task.escalation_channels"))
        if emergency and "ha_speaker_tts" not in channels:
            channels.append("ha_speaker_tts")
        return channels

    def _message(
        self,
        *,
        routine_name: str,
        step_text: str,
        reason: str,
        emergency: bool,
        takeover_url: str,
        transcript: list[str],
    ) -> str:
        priority = "Emergency" if emergency else "Help requested"
        reason_text = _human_reason(reason)
        parts = [
            f"{priority}: guided routine '{routine_name}' needs caregiver attention.",
            f"Reason: {reason_text}.",
            f"Current instruction: {step_text}",
            f"Take over: {takeover_url}",
        ]
        if transcript:
            parts.append("Recent transcript: " + " | ".join(transcript[-5:]))
        return " ".join(parts)

    def _recent_transcript(self, conversation_session_id: int | None) -> list[str]:
        conversation_manager = self._conversation_manager
        if conversation_manager is None or conversation_session_id is None:
            return []
        turns = conversation_manager.get_recent_turns(conversation_session_id, limit=5)
        return [f"{turn['actor']}: {turn['content']}" for turn in turns]

    async def _broadcast_escalation(
        self,
        session: GuidedSession,
        *,
        reason: str,
        emergency: bool,
        detail: dict[str, Any],
    ) -> None:
        event = GuidedEscalationEvent(
            session_id=session.id,
            routine_id=session.routine_id,
            person_id=session.person_id,
            status=session.status,
            step_ord=session.current_step_ord,
            reason=reason,
            emergency=emergency,
            urgent=emergency,
            takeover_url=self._takeover_url(session.id),
            detail=detail,
            at=session.last_activity_at,
        )
        payload = event.model_dump(mode="json")
        if self._ws_manager is not None:
            await self._ws_manager.broadcast(payload)
        if self._admin_ws_broadcaster is not None:
            await self._admin_ws_broadcaster(payload)

    def _takeover_url(self, session_id: int) -> str:
        return f"/admin/guided-sessions/{session_id}"


def _current_step(steps: list[RoutineStep], ord_: int) -> RoutineStep | None:
    for step in steps:
        if step.ord == ord_:
            return step
    return None


def _human_reason(reason: str) -> str:
    if reason == "hazard_active":
        return "the stove or another hazard may still be active while she is away"
    return reason.replace("_", " ")
