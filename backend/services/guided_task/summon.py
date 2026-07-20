"""Presence-gated start and summon flow (M29).

Depends on ``runtime.py`` (``maybe_skip_step``) and ``presentation.py``
(``speak``), both already-built collaborators injected by the façade.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.presentation import Presentation
from backend.services.guided_task.runtime import Runtime
from backend.services.interactive_session.pipeline_link import schedule_session_timeout

logger = get_logger(__name__)


class Summon:
    """Routine start, presence-based summon, and summon re-check."""

    def __init__(
        self,
        ctx: RuntimeContext,
        runtime: Runtime,
        presentation: Presentation,
    ) -> None:
        self._ctx = ctx
        self._runtime = runtime
        self._presentation = presentation

    async def start(
        self,
        routine_id: int,
        person_id: str,
        *,
        execution_id: int | None = None,
        surface_id: str | None = None,
    ) -> GuidedSession:
        return await self.request_start(
            routine_id,
            person_id,
            execution_id=execution_id,
            surface_id=surface_id,
            require_presence=False,
        )

    async def request_start(
        self,
        routine_id: int,
        person_id: str,
        *,
        execution_id: int | None = None,
        surface_id: str | None = None,
        require_presence: bool = True,
        summon_timeout_s: int = 300,
    ) -> GuidedSession:
        ctx = self._ctx
        now = ctx.now()
        routine, steps = ctx.load_routine_and_steps(routine_id)
        if routine.person_id != person_id:
            logger.warning(
                "guided_start_person_mismatch",
                routine_id=routine_id,
                routine_person_id=routine.person_id,
                person_id=person_id,
            )
            raise ValidationError("Routine does not belong to the requested person")
        live = ctx.store.get_live_session_for_person(person_id)
        if live is not None:
            logger.warning("guided_live_session_exists", person_id=person_id, session_id=live.id)
            raise ConflictError(f"Live guided session already exists for person '{person_id}'")

        if not require_presence:
            session = ctx.store.create_session(
                routine_id=routine_id,
                person_id=person_id,
                status="active",
                execution_id=execution_id,
                surface_id=surface_id,
                now=now,
            )
            return await self._begin_session(session.id, routine=routine, steps=steps, now=now)

        location = await self._current_location(person_id)
        selected_surface_id = surface_id
        if selected_surface_id is None and location is not None and location.room_id is not None:
            surfaces = self._surfaces_in_room(location.room_id)
            if surfaces:
                selected_surface_id = surfaces[0].id

        if selected_surface_id is not None and self._has_live_realtime_session():
            session = ctx.store.create_session(
                routine_id=routine_id,
                person_id=person_id,
                status="active",
                execution_id=execution_id,
                surface_id=selected_surface_id,
                now=now,
            )
            return await self._begin_session(session.id, routine=routine, steps=steps, now=now)

        session = ctx.store.create_session(
            routine_id=routine_id,
            person_id=person_id,
            status="summoning",
            execution_id=execution_id,
            surface_id=selected_surface_id,
            now=now,
        )
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="summon_started",
            step_ord=None,
            actor="system",
            detail={"summon_timeout_s": summon_timeout_s},
        )
        await self.announce_summon(
            session=session,
            routine=routine,
            room_name=self._location_room_name(location),
            broad=selected_surface_id is None,
        )
        self._schedule_summon_recheck(session.id, summon_timeout_s, now)
        if selected_surface_id is not None:
            await self._cross_check_surface(selected_surface_id, person_id)
        return session

    async def on_session_opened(self, conversation_session_id: int | None = None) -> None:
        """Best-effort hook called when a realtime companion session opens.

        Invoked fire-and-forget from the websocket connect path, so it must never
        raise into the audio loop: a failure to re-check one summoning session is
        logged and the rest are still attempted. ``conversation_session_id`` is the
        ``conversation_sessions`` row the just-opened realtime session created; it
        links any live guided session that does not yet have a linked conversation
        so escalation and detail reads see her actual turns (M24).
        """
        ctx = self._ctx
        if conversation_session_id is not None:
            for session in ctx.store.list_live_sessions():
                if session.status not in {"summoning", "active", "waiting"}:
                    continue
                if session.conversation_session_id is not None:
                    continue
                try:
                    ctx.link_conversation(
                        session, conversation_session_id, now=ctx.now(), actor="system"
                    )
                except Exception:
                    logger.exception("guided_on_session_opened_link_failed", session_id=session.id)

        for session in ctx.store.list_summoning_sessions():
            try:
                summon_timeout_s = ctx.store.summon_timeout_for(session.id)
                if summon_timeout_s is None:
                    summon_timeout_s = ctx.settings.as_int("guided_task.step_timeout_s")
                    logger.warning(
                        "guided_summon_budget_fallback",
                        session_id=session.id,
                        fallback_summon_timeout_s=summon_timeout_s,
                    )
                await self.summon_recheck(session.id, summon_timeout_s)
            except Exception:
                logger.exception("guided_on_session_opened_recheck_failed", session_id=session.id)

    async def _begin_session(
        self,
        session_id: int,
        *,
        routine: Routine | None = None,
        steps: list[RoutineStep] | None = None,
        now: datetime | None = None,
    ) -> GuidedSession:
        ctx = self._ctx
        begin_at = now or ctx.now()
        session = ctx.store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        if routine is None or steps is None:
            routine, steps = ctx.load_routine_and_steps(session.routine_id)
        updated = ctx.store.update_session(
            session_id,
            status="active",
            current_step_ord=0,
            attempts=0,
            last_activity_at=begin_at,
        )
        if updated is None:
            raise NotFoundError("Guided session", session_id)
        if updated.conversation_session_id is None and self._has_live_realtime_session():
            live_conversation_id = ctx.ws_manager.current_conversation_session_id
            if live_conversation_id is not None:
                updated = ctx.link_conversation(
                    updated, live_conversation_id, now=begin_at, actor="system"
                )
        step = steps[0]
        ctx.store.add_event(
            session_id=session_id,
            at=begin_at,
            kind="step_entered",
            step_ord=step.ord,
            actor="system",
        )
        skipped_further = await self._runtime.maybe_skip_step(
            session=updated,
            routine=routine,
            steps=steps,
            step=step,
            now=begin_at,
            speak_on_advance=True,
        )
        if skipped_further:
            return ctx.require_session(session_id)
        await self._presentation.speak(updated, step, is_retry=False)
        ctx.schedule_timeout(
            updated, routine, step, begin_at, finalize=self._runtime.on_step_timeout
        )
        return updated

    async def summon_recheck(self, session_id: int, summon_timeout_s: int) -> None:
        ctx = self._ctx
        now = ctx.now()
        session = ctx.store.get_session(session_id)
        if session is None or session.status != "summoning":
            return
        routine, steps = ctx.load_routine_steps(session.routine_id)
        if (now - session.started_at).total_seconds() > summon_timeout_s:
            ctx.mark_abandoned(session.id, now=now, outcome="summon_timeout")
            ctx.store.add_event(
                session_id=session.id,
                at=now,
                kind="session_abandoned",
                step_ord=None,
                actor="system",
                detail={"outcome": "summon_timeout"},
            )
            logger.info("guided_summon_timeout", session_id=session.id, person_id=session.person_id)
            return

        location = await self._current_location(session.person_id)
        surface_id = session.surface_id
        if surface_id is None and location is not None and location.room_id is not None:
            surfaces = self._surfaces_in_room(location.room_id)
            if surfaces:
                surface_id = surfaces[0].id
                ctx.store.update_session(session.id, surface_id=surface_id, last_activity_at=now)

        if surface_id is not None and self._has_live_realtime_session():
            await self._begin_session(session.id, routine=routine, steps=steps, now=now)
            return

        if ctx.store.count_events(session_id=session.id, kind="summon_announced") <= 1:
            await self.announce_summon(
                session=session,
                routine=routine,
                room_name=self._location_room_name(location),
                broad=surface_id is None,
            )
        self._schedule_summon_recheck(session.id, summon_timeout_s, now)

    async def _current_location(self, person_id: str) -> Any | None:
        person_location = self._ctx.person_location_service
        if person_location is None:
            return None
        return await person_location.where_is(person_id)

    def _surfaces_in_room(self, room_id: int) -> list[Any]:
        companion_surfaces = self._ctx.companion_surface_service
        if companion_surfaces is None:
            return []
        return companion_surfaces.surfaces_in_room(room_id)

    def _has_live_realtime_session(self) -> bool:
        ws_manager = self._ctx.ws_manager
        if ws_manager is None:
            return False
        # TODO(multi-surface): route websocket presence by companion surface id.
        has_connections = ws_manager.has_connections
        if callable(has_connections):
            return bool(has_connections())
        return bool(has_connections)

    def _location_room_name(self, location: Any | None) -> str:
        if location is None:
            return "home"
        room_name = getattr(location, "room_name", None)
        if room_name:
            return str(room_name)
        room_id = getattr(location, "room_id", None)
        return f"room {room_id}" if room_id is not None else "home"

    async def announce_summon(
        self,
        *,
        session: GuidedSession,
        routine: Routine,
        room_name: str,
        broad: bool,
    ) -> None:
        ctx = self._ctx
        channels = routine.summon_channels_override or ctx.settings.as_list(
            "guided_task.summon_channels"
        )
        resolved_language = (
            routine.language_override or ctx.settings.get("tts.default_language") or "en"
        )
        summon_messages = ctx.settings.get("guided_task.summon_messages", {}) or {}
        message = summon_messages.get(resolved_language)
        if message is None:
            logger.warning(
                "guided_summon_language_missing",
                session_id=session.id,
                language=resolved_language,
            )
            resolved_language = "en"
            message = summon_messages.get(resolved_language)
        if message is None:
            logger.error("guided_summon_message_config_missing", session_id=session.id)
            return
        dispatcher = ctx.notification_dispatcher
        if dispatcher is None:
            logger.warning(
                "guided_summon_announce_skipped",
                session_id=session.id,
                reason="notification_dispatcher_unavailable",
            )
        else:
            try:
                await dispatcher.dispatch(
                    alert_level="reminder",
                    message=message,
                    room_name=room_name,
                    rule_config={"channels": channels, "tts_language": resolved_language},
                )
            except Exception:
                logger.exception("guided_summon_announce_failed", session_id=session.id)
        ctx.store.add_event(
            session_id=session.id,
            at=ctx.now(),
            kind="summon_announced",
            step_ord=None,
            actor="system",
            detail={
                "channels": channels,
                "room_name": room_name,
                "broad": broad,
                "language": resolved_language,
            },
        )
        logger.info(
            "guided_summon_announced",
            session_id=session.id,
            room_name=room_name,
            channels=channels,
            broad=broad,
            language=resolved_language,
        )

    async def _cross_check_surface(self, surface_id: str, person_id: str) -> None:
        companion_surfaces = self._ctx.companion_surface_service
        if companion_surfaces is None:
            return
        await companion_surfaces.cross_check_room(surface_id, person_id)

    def _schedule_summon_recheck(
        self,
        session_id: int,
        summon_timeout_s: int,
        now: datetime,
    ) -> None:
        from types import SimpleNamespace

        interval_s = max(1, min(30, summon_timeout_s // 4))
        scheduler = self._ctx.scheduler
        if scheduler is not None and not hasattr(scheduler, "apscheduler"):
            scheduler = SimpleNamespace(apscheduler=scheduler)
        schedule_session_timeout(
            scheduler,
            job_id=f"guided_summon_recheck_{session_id}",
            run_at=now + timedelta(seconds=interval_s),
            finalize=self.summon_recheck,
            args=[session_id, summon_timeout_s],
        )
