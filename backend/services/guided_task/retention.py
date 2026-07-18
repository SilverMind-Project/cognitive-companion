"""Retention pruning and episodic-memory write on session completion (M29).

Leaf module: depends only on ``RuntimeContext``. ``runtime.py`` calls
``write_session_observation`` from the ``complete()`` terminal path.
"""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from backend.core.logging import get_logger
from backend.integrations.semantic_memory_client import ObservationCreate
from backend.models.guided_task import GuidedSession
from backend.services.guided_task.context import RuntimeContext

logger = get_logger(__name__)


class Retention:
    """Transcript/event retention pruning and episodic session summaries."""

    def __init__(self, ctx: RuntimeContext) -> None:
        self._ctx = ctx

    async def prune_retained_data(self) -> dict[str, int]:
        ctx = self._ctx
        days = ctx.settings.as_int("guided_task.transcript_retention_days")
        cutoff = ctx.now() - timedelta(days=days)
        transcript_sessions = 0
        conversation_manager = ctx.conversation_manager
        if conversation_manager is not None:
            conversation_session_ids = ctx.store.list_prunable_conversation_session_ids(cutoff)
            # A conversation shared with the realtime companion may carry non-guided
            # turns too; pruning it once its linked guided session is 30+ days old
            # matches the existing global conversation TTL policy already bounding
            # reads (ConversationManager.ttl_minutes), so this is acceptable.
            transcript_sessions = conversation_manager.prune_sessions(conversation_session_ids)
        events = ctx.store.prune_events_before(cutoff)
        sessions = ctx.store.prune_sessions_before(cutoff)
        logger.info(
            "guided_retention_pruned",
            events=events,
            sessions=sessions,
            transcript_sessions=transcript_sessions,
            retention_days=days,
        )
        return {
            "events": events,
            "sessions": sessions,
            "transcript_sessions": transcript_sessions,
        }

    async def write_session_observation(self, session: GuidedSession) -> None:
        ctx = self._ctx
        memory = ctx.semantic_memory_client
        if memory is None:
            logger.info(
                "guided_memory_write_skipped",
                session_id=session.id,
                reason="semantic_memory_unavailable",
            )
            return
        routine = ctx.store.get_routine(session.routine_id)
        routine_name = routine.name if routine is not None else f"routine {session.routine_id}"
        events = ctx.store.list_events(session_id=session.id, limit=200)
        completed_steps = sorted(
            {
                event.step_ord
                for event in events
                if event.kind == "step_completed" and event.step_ord is not None
            }
        )
        skipped_steps = sorted(
            {
                event.step_ord
                for event in events
                if event.kind == "step_skipped" and event.step_ord is not None
            }
        )
        stalled_steps = sorted(
            {
                event.step_ord
                for event in events
                if event.kind in {"retry", "step_blocked"} and event.step_ord is not None
            }
        )
        duration_s = 0
        if session.completed_at is not None:
            duration_s = max(0, int((session.completed_at - session.started_at).total_seconds()))
        local_hour = session.started_at.astimezone(
            ZoneInfo(ctx.settings.as_str("app.timezone"))
        ).strftime("%H:%M")
        description = (
            f"Guided routine '{routine_name}' ended with outcome '{session.outcome}'. "
            f"Duration {duration_s} seconds. Started near local time {local_hour}. "
            f"Completed steps: {completed_steps or 'none'}. "
            f"Skipped steps: {skipped_steps or 'none'}. "
            f"Stalled steps: {stalled_steps or 'none'}."
        )
        try:
            await memory.create_observation(
                ObservationCreate(
                    room_id="guided_task",
                    description=description,
                    object_list=[routine_name],
                    hazard_flags=[],
                    source="guided_task",
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "guided_memory_write_failed",
                session_id=session.id,
                error=str(exc),
            )
