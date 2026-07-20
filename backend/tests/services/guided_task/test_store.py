"""Tests for GuidedTaskStore (M25, G19)."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from backend.core.exceptions import ConflictError
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.domain import UNIQUE_SESSION_STATUSES
from backend.services.guided_task.service import GuidedTaskService
from backend.services.guided_task.store import GuidedTaskStore


def test_one_live_session_index_predicate_matches_domain_constant(db_session):
    """The DB predicate and services/guided_task/domain.py must not drift (G19)."""
    indexdef = db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'uq_guided_sessions_one_live_per_person'"
        )
    ).scalar_one()

    statuses_in_predicate = set(re.findall(r"'([a-z_]+)'", indexdef))

    assert statuses_in_predicate == set(UNIQUE_SESSION_STATUSES)
    assert "UNIQUE" in indexdef.upper()


def _add_routine(db_session, person_id: str = "person-1") -> Routine:
    db_session.add(HouseholdMember(id=person_id, name="Ruth"))
    db_session.commit()
    routine = Routine(name="Make tea", person_id=person_id, is_enabled=True)
    routine.steps.append(RoutineStep(ord=0, prompt_template="Boil water."))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)
    return routine


def test_create_session_second_live_session_raises_conflict(db_factory, db_session):
    """The unique index, not just the read-check, blocks a second live session."""
    routine = _add_routine(db_session)
    store = GuidedTaskStore(db_factory)
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)

    store.create_session(
        routine_id=routine.id,
        person_id="person-1",
        status="active",
        execution_id=None,
        surface_id=None,
        now=now,
    )

    with pytest.raises(ConflictError):
        store.create_session(
            routine_id=routine.id,
            person_id="person-1",
            status="active",
            execution_id=None,
            surface_id=None,
            now=now,
        )

    db_session.expire_all()
    count = db_session.query(GuidedSession).filter(GuidedSession.person_id == "person-1").count()
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_request_start_only_one_session_created(db_factory, db_session):
    routine = _add_routine(db_session)
    service = GuidedTaskService(db_factory=db_factory)

    results = await asyncio.gather(
        service.request_start(routine.id, "person-1", require_presence=False),
        service.request_start(routine.id, "person-1", require_presence=False),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], ConflictError)

    db_session.expire_all()
    count = db_session.query(GuidedSession).filter(GuidedSession.person_id == "person-1").count()
    assert count == 1
