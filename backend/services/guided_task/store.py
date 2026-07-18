"""Persistence helpers for guided-task services."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.services.guided_task.domain import LIVE_STATUSES


class GuidedTaskStore:
    """Small SQLAlchemy store with explicit session ownership."""

    def __init__(self, db_factory: Callable[[], Session]) -> None:
        self._db_factory = db_factory

    def get_routine(self, routine_id: int) -> Routine | None:
        db = self._db_factory()
        try:
            return db.get(Routine, routine_id)
        finally:
            db.close()

    def list_routines(
        self, *, person_id: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Routine], int]:
        db = self._db_factory()
        try:
            stmt = select(Routine).order_by(Routine.id.desc())
            if person_id is not None:
                stmt = stmt.where(Routine.person_id == person_id)
            total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
            return rows, total
        finally:
            db.close()

    def create_routine(self, **values: Any) -> Routine:
        db = self._db_factory()
        try:
            routine = Routine(**values)
            db.add(routine)
            db.commit()
            db.refresh(routine)
            return routine
        finally:
            db.close()

    def update_routine(self, routine_id: int, **values: Any) -> Routine | None:
        db = self._db_factory()
        try:
            routine = db.get(Routine, routine_id)
            if routine is None:
                return None
            for key, value in values.items():
                setattr(routine, key, value)
            db.commit()
            db.refresh(routine)
            return routine
        finally:
            db.close()

    def delete_routine(self, routine_id: int) -> bool:
        db = self._db_factory()
        try:
            routine = db.get(Routine, routine_id)
            if routine is None:
                return False
            db.delete(routine)
            db.commit()
            return True
        finally:
            db.close()

    def replace_steps(self, routine_id: int, steps_data: list[dict[str, Any]]) -> list[RoutineStep]:
        db = self._db_factory()
        try:
            db.query(RoutineStep).filter(RoutineStep.routine_id == routine_id).delete(
                synchronize_session=False
            )
            new_steps = [RoutineStep(routine_id=routine_id, **s) for s in steps_data]
            db.add_all(new_steps)
            db.commit()
            for step in new_steps:
                db.refresh(step)
            return new_steps
        finally:
            db.close()

    def count_steps(self, routine_id: int) -> int:
        db = self._db_factory()
        try:
            return int(
                db.execute(
                    select(func.count()).where(RoutineStep.routine_id == routine_id)
                ).scalar_one()
            )
        finally:
            db.close()

    def list_sessions(
        self,
        *,
        person_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[GuidedSession], int]:
        db = self._db_factory()
        try:
            stmt = select(GuidedSession).order_by(GuidedSession.started_at.desc())
            if person_id is not None:
                stmt = stmt.where(GuidedSession.person_id == person_id)
            if status is not None:
                stmt = stmt.where(GuidedSession.status == status)
            total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
            return rows, total
        finally:
            db.close()

    def list_steps(self, routine_id: int) -> list[RoutineStep]:
        db = self._db_factory()
        try:
            stmt = (
                select(RoutineStep)
                .where(RoutineStep.routine_id == routine_id)
                .order_by(RoutineStep.ord)
            )
            return list(db.execute(stmt).scalars().all())
        finally:
            db.close()

    def create_session(
        self,
        *,
        routine_id: int,
        person_id: str,
        status: str,
        execution_id: int | None,
        surface_id: str | None,
        now: datetime,
    ) -> GuidedSession:
        db = self._db_factory()
        try:
            session = GuidedSession(
                routine_id=routine_id,
                person_id=person_id,
                execution_id=execution_id,
                surface_id=surface_id,
                status=status,
                current_step_ord=0,
                attempts=0,
                started_at=now,
                last_activity_at=now,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
        finally:
            db.close()

    def get_session(self, session_id: int) -> GuidedSession | None:
        db = self._db_factory()
        try:
            return db.get(GuidedSession, session_id)
        finally:
            db.close()

    def get_live_session_for_person(self, person_id: str) -> GuidedSession | None:
        db = self._db_factory()
        try:
            stmt = (
                select(GuidedSession)
                .where(
                    GuidedSession.person_id == person_id,
                    GuidedSession.status.in_(LIVE_STATUSES),
                )
                .order_by(GuidedSession.started_at.desc())
            )
            return db.execute(stmt).scalars().first()
        finally:
            db.close()

    def list_live_sessions(self) -> list[GuidedSession]:
        db = self._db_factory()
        try:
            stmt = select(GuidedSession).where(GuidedSession.status.in_(LIVE_STATUSES))
            return list(db.execute(stmt).scalars().all())
        finally:
            db.close()

    def list_summoning_sessions(self) -> list[GuidedSession]:
        db = self._db_factory()
        try:
            stmt = select(GuidedSession).where(GuidedSession.status == "summoning")
            return list(db.execute(stmt).scalars().all())
        finally:
            db.close()

    def update_session(self, session_id: int, **values: Any) -> GuidedSession | None:
        db = self._db_factory()
        try:
            session = db.get(GuidedSession, session_id)
            if session is None:
                return None
            for key, value in values.items():
                setattr(session, key, value)
            db.commit()
            db.refresh(session)
            return session
        finally:
            db.close()

    def add_event(
        self,
        *,
        session_id: int,
        at: datetime,
        kind: str,
        step_ord: int | None,
        actor: str | None,
        detail: dict | None = None,
    ) -> GuidedSessionEvent:
        db = self._db_factory()
        try:
            event = GuidedSessionEvent(
                session_id=session_id,
                at=at,
                kind=kind,
                step_ord=step_ord,
                actor=actor,
                detail=detail,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            return event
        finally:
            db.close()

    def latest_event_at(
        self, *, session_id: int, kind: str, step_ord: int | None
    ) -> datetime | None:
        db = self._db_factory()
        try:
            step_filter = (
                GuidedSessionEvent.step_ord.is_(None)
                if step_ord is None
                else GuidedSessionEvent.step_ord == step_ord
            )
            stmt = (
                select(GuidedSessionEvent.at)
                .where(
                    GuidedSessionEvent.session_id == session_id,
                    GuidedSessionEvent.kind == kind,
                    step_filter,
                )
                .order_by(GuidedSessionEvent.at.desc())
            )
            return db.execute(stmt).scalars().first()
        finally:
            db.close()

    def count_events(self, *, session_id: int, kind: str) -> int:
        db = self._db_factory()
        try:
            return int(
                db.query(GuidedSessionEvent)
                .filter(
                    GuidedSessionEvent.session_id == session_id,
                    GuidedSessionEvent.kind == kind,
                )
                .count()
            )
        finally:
            db.close()

    def list_events(self, *, session_id: int, limit: int = 20) -> list[GuidedSessionEvent]:
        db = self._db_factory()
        try:
            stmt = (
                select(GuidedSessionEvent)
                .where(GuidedSessionEvent.session_id == session_id)
                .order_by(GuidedSessionEvent.at.desc(), GuidedSessionEvent.id.desc())
                .limit(limit)
            )
            events = list(db.execute(stmt).scalars().all())
            events.reverse()
            return events
        finally:
            db.close()

    def prune_events_before(self, cutoff: datetime) -> int:
        db = self._db_factory()
        try:
            rows = (
                db.query(GuidedSessionEvent)
                .filter(GuidedSessionEvent.at < cutoff)
                .delete(synchronize_session=False)
            )
            db.commit()
            return rows
        finally:
            db.close()

    def list_prunable_conversation_session_ids(self, cutoff: datetime) -> list[int]:
        """Conversation ids linked to completed sessions before ``cutoff``.

        Excludes any conversation still linked to a live guided session, so
        retention pruning never deletes a conversation a resident or caregiver
        is actively using.
        """
        db = self._db_factory()
        try:
            live_conversation_ids = select(GuidedSession.conversation_session_id).where(
                GuidedSession.status.in_(LIVE_STATUSES),
                GuidedSession.conversation_session_id.isnot(None),
            )
            stmt = (
                select(GuidedSession.conversation_session_id)
                .where(
                    GuidedSession.completed_at.isnot(None),
                    GuidedSession.completed_at < cutoff,
                    GuidedSession.conversation_session_id.isnot(None),
                    GuidedSession.conversation_session_id.not_in(live_conversation_ids),
                )
                .distinct()
            )
            return [
                int(row) for row in db.execute(stmt).scalars().all() if row is not None
            ]
        finally:
            db.close()

    def prune_sessions_before(self, cutoff: datetime) -> int:
        db = self._db_factory()
        try:
            rows = (
                db.query(GuidedSession)
                .filter(
                    GuidedSession.completed_at.isnot(None),
                    GuidedSession.completed_at < cutoff,
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            return rows
        finally:
            db.close()
