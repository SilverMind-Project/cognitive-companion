"""Tests for GuidedMemoryBridge (DL-M05).

Covers the DL9 headline (abandon never writes a ledger row, but always
writes the episode), the ledger open/close, episode writes through
scene_intel with kind/person_id, embedder degradation, and the
best-effort failure trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.models.person import ActivitySession, HouseholdMember
from backend.services.activity_session import ActivitySessionService
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.memory_bridge import (
    GuidedMemoryBridge,
    build_episode_description,
)
from backend.services.scene_intel.types import SceneIntelRecord


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now


@dataclass
class _SceneIntel:
    drafts: list = field(default_factory=list)
    raise_on_persist: bool = False

    async def persist_observation(self, draft):
        if self.raise_on_persist:
            raise RuntimeError("scene_intel unavailable")
        self.drafts.append(draft)
        return SceneIntelRecord(observation_id=len(self.drafts))


@dataclass
class _EmbeddingClient:
    calls: list = field(default_factory=list)
    raise_on_embed: bool = False

    async def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        if self.raise_on_embed:
            raise RuntimeError("triton unavailable")
        return [0.1, 0.2, 0.3]


def _settings() -> Settings:
    return Settings.from_dict({"app": {"timezone": "America/New_York"}})


def _seed_routine(db_session, *, activity_type: str | None, steps: int = 1) -> Routine:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(
        name="Make tea",
        person_id="resident-1",
        is_enabled=True,
        activity_type=activity_type,
    )
    for ord_ in range(steps):
        routine.steps.append(RoutineStep(ord=ord_, prompt_template=f"Step {ord_}"))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)
    return routine


def _seed_session(
    db_session, routine: Routine, *, status: str, started_at: datetime, completed_at: datetime
) -> GuidedSession:
    session = GuidedSession(
        routine_id=routine.id,
        person_id=routine.person_id,
        status=status,
        current_step_ord=0,
        attempts=0,
        started_at=started_at,
        completed_at=completed_at,
        last_activity_at=completed_at,
        outcome=status,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


def _make_ctx(
    db_factory,
    *,
    now: datetime,
    scene_intel=None,
    embedding_client=None,
    activity_service=None,
) -> RuntimeContext:
    return RuntimeContext(
        db_factory=db_factory,
        settings=_settings(),
        time_fn=_Clock(now),
        scene_intel=scene_intel,
        embedding_client=embedding_client,
        activity_service=activity_service,
    )


@pytest.mark.asyncio
async def test_completed_with_activity_type_writes_ledger_row(db_session, db_factory):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    routine = _seed_routine(db_session, activity_type="medication")
    started_at = datetime(2026, 7, 21, 11, 50, tzinfo=UTC)
    session = _seed_session(db_session, routine, status="completed", started_at=started_at, completed_at=now)
    activity_service = ActivitySessionService(db_factory)
    ctx = _make_ctx(db_factory, now=now, activity_service=activity_service)
    bridge = GuidedMemoryBridge(ctx)

    await bridge.on_session_terminal(session)

    rows = db_session.execute(
        select(ActivitySession).where(ActivitySession.person_id == "resident-1")
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.activity_type == "medication"
    assert row.status == "closed"
    assert row.duration_minutes == 10
    # Provenance and confidence are first-class columns, not metadata keys:
    # a guided completion is the ledger's highest evidence grade.
    assert row.source == "guided_companion"
    assert row.confidence == 0.95
    assert row.metadata_json["guided_session_id"] == session.id
    assert row.metadata_json["routine_id"] == routine.id
    # The close path must not drop the open path's metadata (plain-JSON
    # in-place mutation used to discard closed_via here).
    assert row.metadata_json["closed_via"] == "explicit"


@pytest.mark.asyncio
async def test_completed_without_activity_type_writes_no_ledger_row(db_session, db_factory):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    routine = _seed_routine(db_session, activity_type=None)
    session = _seed_session(db_session, routine, status="completed", started_at=now, completed_at=now)
    activity_service = ActivitySessionService(db_factory)
    ctx = _make_ctx(db_factory, now=now, activity_service=activity_service)
    bridge = GuidedMemoryBridge(ctx)

    await bridge.on_session_terminal(session)

    rows = db_session.execute(
        select(ActivitySession).where(ActivitySession.person_id == "resident-1")
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_abandoned_writes_episode_but_no_ledger_row(db_session, db_factory):
    """DL9 headline: an abandoned medication routine must never look like 'taken'."""
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    routine = _seed_routine(db_session, activity_type="medication")
    session = _seed_session(db_session, routine, status="abandoned", started_at=now, completed_at=now)
    activity_service = ActivitySessionService(db_factory)
    scene_intel = _SceneIntel()
    ctx = _make_ctx(
        db_factory, now=now, activity_service=activity_service, scene_intel=scene_intel
    )
    bridge = GuidedMemoryBridge(ctx)

    await bridge.on_session_terminal(session)

    rows = db_session.execute(
        select(ActivitySession).where(ActivitySession.person_id == "resident-1")
    ).scalars().all()
    assert rows == []
    assert len(scene_intel.drafts) == 1
    assert "outcome 'abandoned'" in scene_intel.drafts[0].description


def test_episode_summary_deterministic():
    session = GuidedSession(
        id=1,
        routine_id=1,
        person_id="resident-1",
        status="completed",
        current_step_ord=1,
        attempts=0,
        started_at=datetime(2026, 7, 21, 9, 0, tzinfo=UTC),
        completed_at=datetime(2026, 7, 21, 9, 14, tzinfo=UTC),
        outcome="completed",
    )
    events = [
        _fake_event(kind="step_completed", step_ord=0),
        _fake_event(kind="step_completed", step_ord=1),
        _fake_event(kind="retry", step_ord=1),
        _fake_event(kind="retry", step_ord=1),
        _fake_event(kind="retry", step_ord=1),
        _fake_event(kind="escalation", step_ord=1),
    ]

    description = build_episode_description("Make tea", session, events, "America/New_York")

    assert description == (
        "Guided routine 'Make tea' ended with outcome 'completed'. "
        "Duration 840 seconds. Started near local time 05:00. "
        "Completed steps: [0, 1]. "
        "Skipped steps: none. "
        "Stalled steps: [1]. "
        "Total retries: 3 (step 1 retried 3x). Escalations: 1."
    )


@pytest.mark.asyncio
async def test_episode_written_through_scene_intel_with_kind_and_person(db_session, db_factory):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    routine = _seed_routine(db_session, activity_type=None)
    session = _seed_session(db_session, routine, status="completed", started_at=now, completed_at=now)
    scene_intel = _SceneIntel()
    ctx = _make_ctx(db_factory, now=now, scene_intel=scene_intel)
    bridge = GuidedMemoryBridge(ctx)

    await bridge.on_session_terminal(session)

    assert len(scene_intel.drafts) == 1
    draft = scene_intel.drafts[0]
    assert draft.kind == "guided_episode"
    assert draft.person_id == "resident-1"
    assert draft.source == "guided_companion"
    assert draft.object_list == ["Make tea"]
    assert draft.room_id is None


@pytest.mark.asyncio
async def test_embedder_unavailable_still_writes_episode(db_session, db_factory):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    routine = _seed_routine(db_session, activity_type=None)
    session = _seed_session(db_session, routine, status="completed", started_at=now, completed_at=now)
    scene_intel = _SceneIntel()
    embedding_client = _EmbeddingClient(raise_on_embed=True)
    ctx = _make_ctx(
        db_factory, now=now, scene_intel=scene_intel, embedding_client=embedding_client
    )
    bridge = GuidedMemoryBridge(ctx)

    await bridge.on_session_terminal(session)

    assert len(scene_intel.drafts) == 1
    assert scene_intel.drafts[0].description_embedding == []


@pytest.mark.asyncio
async def test_bridge_failure_never_raises_and_appends_failure_event(db_session, db_factory):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    routine = _seed_routine(db_session, activity_type=None)
    session = _seed_session(db_session, routine, status="completed", started_at=now, completed_at=now)
    scene_intel = _SceneIntel(raise_on_persist=True)
    ctx = _make_ctx(db_factory, now=now, scene_intel=scene_intel)
    bridge = GuidedMemoryBridge(ctx)

    await bridge.on_session_terminal(session)  # must not raise

    events = ctx.store.list_events(session_id=session.id, limit=20)
    failure_events = [e for e in events if e.kind == "memory_write_failed"]
    assert len(failure_events) == 1
    assert failure_events[0].detail["target"] == "episode"


def _fake_event(*, kind: str, step_ord: int | None):
    from types import SimpleNamespace

    return SimpleNamespace(kind=kind, step_ord=step_ord)
