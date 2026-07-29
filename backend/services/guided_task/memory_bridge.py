"""Guided-session terminal-transition bridge to ledger, memory, and events (DL-M05).

Writes, on every terminal transition (``complete()`` and ``abandon()``):

- an ``ActivitySession`` ledger row, but only when the session actually
  completed and its routine maps to an activity type (DL9: a false "she took
  her medication" is a care-safety hazard, never write on abandon);
- exactly one narrative episodic observation to semantic memory, on every
  terminal outcome (DL7b: the episode records what happened even when
  nothing can be claimed);
- a ``GuidedSessionEvent`` trace (``ledger_recorded`` / ``episode_recorded`` /
  ``memory_write_failed``) so the session timeline shows what was recorded.

Best-effort: a failure in either write is caught, logged, and traced as a
``memory_write_failed`` event. It never raises, so it never fails the
session transition it is attached to (wave-3 rule 12).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine
from backend.models.person import ActivitySourceEnum
from backend.services.guided_task.context import RuntimeContext
from backend.services.scene_intel.types import ObservationDraft

logger = get_logger(__name__)


class GuidedMemoryBridge:
    """Ledger + semantic-memory writer attached to the terminal-transition seam."""

    def __init__(self, ctx: RuntimeContext) -> None:
        self._ctx = ctx

    async def on_session_terminal(self, session: GuidedSession) -> None:
        ctx = self._ctx
        routine = ctx.store.get_routine(session.routine_id)
        if routine is None:
            logger.warning(
                "guided_memory_bridge_routine_missing",
                session_id=session.id,
                routine_id=session.routine_id,
            )
            return

        if session.status == "completed" and routine.activity_type:
            await self._write_ledger(session, routine)

        await self._write_episode(session, routine)

    # ------------------------------------------------------------------
    # Ledger (DL9 headline: completed-only)
    # ------------------------------------------------------------------

    async def _write_ledger(self, session: GuidedSession, routine: Routine) -> None:
        ctx = self._ctx
        activity_service = ctx.activity_service
        if activity_service is None:
            return
        now = ctx.now()
        try:
            # Highest evidence grade in the ledger: she confirmed each step
            # with the companion and the routine reached its terminal
            # "completed" transition, which is the only path that gets here.
            activity_service.open_session(
                person_id=session.person_id,
                activity_type=routine.activity_type,
                room_name=None,
                confidence=0.95,
                started_at=session.started_at,
                start_event_id=None,
                source=ActivitySourceEnum.guided_companion.value,
                metadata={
                    "guided_session_id": session.id,
                    "routine_id": routine.id,
                },
            )
            activity_service.close_session(
                person_id=session.person_id,
                activity_type=routine.activity_type,
                ended_at=session.completed_at or now,
                end_event_id=None,
                closed_via="explicit",
            )
        except Exception as exc:  # noqa: BLE001
            self._record_failure(session, now, target="ledger", error=exc)
            return
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="ledger_recorded",
            step_ord=session.current_step_ord,
            actor="system",
            detail={"activity_type": routine.activity_type},
        )

    # ------------------------------------------------------------------
    # Episodic observation (every terminal outcome)
    # ------------------------------------------------------------------

    async def _write_episode(self, session: GuidedSession, routine: Routine) -> None:
        ctx = self._ctx
        scene_intel = ctx.scene_intel
        if scene_intel is None:
            return
        now = ctx.now()
        try:
            events = ctx.store.list_events(session_id=session.id, limit=200)
            description = build_episode_description(
                routine.name, session, events, ctx.settings.as_str("app.timezone")
            )
            embedding = await self._embed(description, session)
            draft = ObservationDraft(
                room_id=None,
                description=description,
                object_list=[routine.name],
                hazard_flags=[],
                description_embedding=embedding,
                source="guided_companion",
                person_id=session.person_id,
                kind="guided_episode",
                # The episode is recorded at its terminal outcome, so `now` is
                # the real observation time rather than an approximation.
                observed_at=now,
            )
            record = await scene_intel.persist_observation(draft)
        except Exception as exc:  # noqa: BLE001
            self._record_failure(session, now, target="episode", error=exc)
            return
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="episode_recorded",
            step_ord=session.current_step_ord,
            actor="system",
            detail={"observation_id": record.observation_id},
        )

    async def _embed(self, description: str, session: GuidedSession) -> list[float]:
        embedding_client = self._ctx.embedding_client
        if embedding_client is None:
            return []
        try:
            return await embedding_client.embed_query(description)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "guided_memory_bridge_embed_unavailable",
                session_id=session.id,
                error=str(exc),
            )
            return []

    def _record_failure(
        self, session: GuidedSession, now: datetime, *, target: str, error: Exception
    ) -> None:
        logger.warning(
            "guided_memory_bridge_error",
            session_id=session.id,
            target=target,
            error=str(error),
        )
        self._ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="memory_write_failed",
            step_ord=session.current_step_ord,
            actor="system",
            detail={"target": target, "error": str(error)},
        )


def build_episode_description(
    routine_name: str,
    session: GuidedSession,
    events: list[GuidedSessionEvent],
    tz_name: str,
) -> str:
    """Deterministic 2-4 sentence episode summary from session events.

    Ported from the pre-M29 ``_write_session_observation`` /
    ``retention.py::write_session_observation`` (routine name, outcome,
    duration, local start hour, completed/skipped/stalled step ordinals),
    extended with total retries, the most-retried step, and escalation
    count (Part D.2). ``RoutineStep`` has no display name, so steps are
    identified by ordinal throughout, matching the pre-existing fields.
    """
    completed_steps = sorted(
        {e.step_ord for e in events if e.kind == "step_completed" and e.step_ord is not None}
    )
    skipped_steps = sorted(
        {e.step_ord for e in events if e.kind == "step_skipped" and e.step_ord is not None}
    )
    stalled_steps = sorted(
        {
            e.step_ord
            for e in events
            if e.kind in {"retry", "step_blocked"} and e.step_ord is not None
        }
    )
    retry_counts: dict[int, int] = {}
    for event in events:
        if event.kind == "retry" and event.step_ord is not None:
            retry_counts[event.step_ord] = retry_counts.get(event.step_ord, 0) + 1
    total_retries = sum(retry_counts.values())
    most_retried_step = max(retry_counts, key=lambda ord_: retry_counts[ord_], default=None)
    escalation_count = sum(1 for event in events if event.kind == "escalation")

    duration_s = 0
    if session.completed_at is not None:
        duration_s = max(0, int((session.completed_at - session.started_at).total_seconds()))
    local_hour = session.started_at.astimezone(ZoneInfo(tz_name)).strftime("%H:%M")

    retry_clause = f"Total retries: {total_retries}"
    if most_retried_step is not None:
        retry_clause += f" (step {most_retried_step} retried {retry_counts[most_retried_step]}x)"
    retry_clause += f". Escalations: {escalation_count}."

    return (
        f"Guided routine '{routine_name}' ended with outcome '{session.outcome}'. "
        f"Duration {duration_s} seconds. Started near local time {local_hour}. "
        f"Completed steps: {completed_steps or 'none'}. "
        f"Skipped steps: {skipped_steps or 'none'}. "
        f"Stalled steps: {stalled_steps or 'none'}. "
        f"{retry_clause}"
    )
