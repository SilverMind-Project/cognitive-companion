"""Tests for DailyLivingHealthService - memory + ledger write-health snapshot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.integrations.semantic_memory_client import ObservationsByDay, WriteHealthResult
from backend.models.person import ActivitySession, ActivityTypeEnum, HouseholdMember
from backend.services.daily_living_health import DailyLivingHealthService


def _make_person(db, person_id="person123"):
    member = HouseholdMember(id=person_id, name="Test Person", is_active=True)
    db.add(member)
    db.flush()
    return member


def _make_session(db, person_id, activity_type, opened_at):
    session = ActivitySession(
        id=f"{person_id}_{activity_type}_{opened_at.isoformat()}",
        person_id=person_id,
        activity_type=activity_type,
        room_name="bedroom",
        opened_at=opened_at,
        closed_at=None,
        status="open",
        timeout_minutes=720,
        duration_minutes=None,
    )
    db.add(session)
    db.flush()
    return session


class _FakeSemanticMemoryClient:
    def __init__(self, result: WriteHealthResult | None):
        self._result = result

    async def get_write_health(self, days: int = 14) -> WriteHealthResult | None:
        return self._result


class TestSnapshotSemanticMemory:
    async def test_snapshot_with_reachable_memory(self, db_factory):
        now = datetime(2026, 7, 21, 14, 0, 0, tzinfo=UTC)
        result = WriteHealthResult(
            last_observation_at=now - timedelta(minutes=5),
            last_movement_at=now - timedelta(minutes=10),
            observations_by_day=[ObservationsByDay(day=now, source="scene_intel", count=3)],
            total_observations=3,
            total_movements=1,
        )
        service = DailyLivingHealthService(
            db_factory,
            _FakeSemanticMemoryClient(result),
            time_fn=lambda: now,
        )

        snapshot = await service.snapshot()

        assert snapshot.semantic_memory.reachable is True
        assert snapshot.semantic_memory.last_observation_at == now - timedelta(minutes=5)
        assert snapshot.semantic_memory.total_observations == 3
        assert snapshot.semantic_memory.total_movements == 1
        assert len(snapshot.semantic_memory.observations_by_day) == 1
        assert snapshot.semantic_memory.stale is False

    async def test_snapshot_memory_unreachable(self, db_factory):
        now = datetime(2026, 7, 21, 14, 0, 0, tzinfo=UTC)
        service = DailyLivingHealthService(
            db_factory,
            _FakeSemanticMemoryClient(None),
            time_fn=lambda: now,
        )

        snapshot = await service.snapshot()

        assert snapshot.semantic_memory.reachable is False
        assert snapshot.semantic_memory.stale is True
        assert snapshot.semantic_memory.last_observation_at is None

    async def test_snapshot_memory_client_none_is_unconfigured(self, db_factory):
        now = datetime(2026, 7, 21, 14, 0, 0, tzinfo=UTC)
        service = DailyLivingHealthService(db_factory, None, time_fn=lambda: now)

        snapshot = await service.snapshot()

        assert snapshot.semantic_memory.reachable is False
        assert snapshot.semantic_memory.stale is True

    async def test_snapshot_stale_thresholds(self, db_factory):
        now = datetime(2026, 7, 21, 14, 0, 0, tzinfo=UTC)
        result = WriteHealthResult(
            last_observation_at=now - timedelta(hours=25),
            last_movement_at=None,
        )
        service = DailyLivingHealthService(
            db_factory,
            _FakeSemanticMemoryClient(result),
            memory_stale_hours=24.0,
            time_fn=lambda: now,
        )

        snapshot = await service.snapshot()

        assert snapshot.semantic_memory.stale is True


class TestActivityLedgerHealth:
    def test_ledger_counts_by_type(self, db_factory):
        now = datetime(2026, 7, 21, 14, 0, 0, tzinfo=UTC)
        db = db_factory()
        try:
            _make_person(db, "person123")
            _make_session(db, "person123", ActivityTypeEnum.sleep, now - timedelta(days=1))
            _make_session(db, "person123", ActivityTypeEnum.sleep, now - timedelta(hours=2))
            _make_session(db, "person123", ActivityTypeEnum.watching_tv, now - timedelta(hours=1))
            db.commit()
        finally:
            db.close()

        service = DailyLivingHealthService(
            db_factory,
            _FakeSemanticMemoryClient(None),
            ledger_stale_hours=48.0,
            time_fn=lambda: now,
        )

        ledger = service._activity_ledger_health()

        by_type = {row.activity_type: row for row in ledger.by_type}
        assert by_type["sleep"].count == 2
        assert by_type["sleep"].last_opened_at == now - timedelta(hours=2)
        assert by_type["watching_tv"].count == 1
        assert ledger.stale is False

    def test_ledger_empty(self, db_factory):
        now = datetime(2026, 7, 21, 14, 0, 0, tzinfo=UTC)
        service = DailyLivingHealthService(
            db_factory,
            _FakeSemanticMemoryClient(None),
            time_fn=lambda: now,
        )

        ledger = service._activity_ledger_health()

        assert ledger.by_type == []
        assert ledger.stale is True
