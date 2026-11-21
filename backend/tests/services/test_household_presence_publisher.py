"""Unit and round-trip tests for HouseholdPresencePublisher and PresenceStatus contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from cts_contracts.household import PresenceStatus as SharedPresenceStatus

from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.integrations.proto.continuoustracking.v1 import household_pb2
from backend.models.person import HouseholdMember
from backend.schemas.identity_readiness import CTSClosedWorldReadiness, CTSIdentityReadiness
from backend.schemas.identity_roster import RosterHealthEnvelope
from backend.services.cts.household_presence_publisher import (
    FIELD_PRESENCE,
    STREAM,
    HouseholdPresencePublisher,
)
from backend.services.identity_readiness_rules import roster_step
from backend.services.occupancy.read_model import OccupancyReadModel
from backend.services.presence.types import PresenceSnapshot, PresenceSource, PresenceStatus


@dataclass
class _FakeRedis:
    entries: list[tuple[str, dict[bytes, bytes]]]

    def __init__(self) -> None:
        self.entries = []

    async def xadd(
        self,
        stream: str,
        fields: dict[bytes, bytes],
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> bytes:
        _ = (maxlen, approximate)
        self.entries.append((stream, fields))
        return f"{len(self.entries)}-0".encode()


class _MutableClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _snapshot(
    person_id: str,
    status: PresenceStatus,
    *,
    confidence: float = 0.9,
    room_id: str | None = None,
    at: datetime,
) -> PresenceSnapshot:
    return PresenceSnapshot(
        person_id=person_id,
        status=status,
        room_id=room_id,
        room_name=room_id,
        confidence=confidence,
        last_seen_at=at,
        dwell_minutes=None,
        sources=(PresenceSource(name="test", confidence=confidence),),
        inferred_at=at,
    )


def _roster_health(*, is_complete: bool, surfaced: int = 0) -> RosterHealthEnvelope:
    return RosterHealthEnvelope(
        members_without_face_enrollment=[],
        active_member_count=2,
        min_face_embeddings=3,
        visitor_clustering_enabled=True,
        surfaced_unnamed_visitor_clusters=surfaced,
        is_complete=is_complete,
        checked_at=datetime(2026, 11, 21, 12, 0, tzinfo=UTC),
    )


def test_presence_status_is_single_shared_enum() -> None:
    assert PresenceStatus is SharedPresenceStatus


@pytest.mark.asyncio
async def test_publisher_round_trip_change_and_heartbeat(db_factory: Any) -> None:
    db = db_factory()
    try:
        db.add_all(
            [
                HouseholdMember(id="alice", name="Alice", is_active=True, is_guest=False),
                HouseholdMember(id="grandma", name="Grandma", is_active=True, is_guest=False),
                HouseholdMember(id="guest-bob", name="Guest Bob", is_active=True, is_guest=True),
            ]
        )
        db.commit()
    finally:
        db.close()

    t0 = datetime.now(UTC)
    clock = _MutableClock(t0)
    redis = _FakeRedis()
    occupancy = OccupancyReadModel(db_factory=None)

    statuses: dict[str, PresenceStatus] = {
        "alice": PresenceStatus.AWAY,
        "grandma": PresenceStatus.PRESENT_ROOM,
        "guest-bob": PresenceStatus.UNKNOWN,
    }

    presence_service = AsyncMock()
    presence_service.get.side_effect = lambda pid, at=None: _snapshot(
        pid,
        statuses[pid],
        confidence=0.9,
        room_id="living_room" if pid == "grandma" else None,
        at=at or clock.now,
    )

    roster_service = AsyncMock()
    roster_service.get_roster_health.return_value = _roster_health(is_complete=True, surfaced=0)
    roster_service.has_recent_surfaced_visitor.return_value = False

    pub = HouseholdPresencePublisher(
        redis_client=redis,
        presence_service=presence_service,
        roster_health_service=roster_service,
        db_factory=db_factory,
        occupancy_read_model=occupancy,
        heartbeat_interval_s=60.0,
        clock=clock,
    )

    # First call publishes immediately.
    assert await pub.publish_if_due() is True
    assert len(redis.entries) == 1
    stream, fields = redis.entries[-1]
    assert stream == STREAM
    decoded = household_pb2.HouseholdPresence()
    decoded.ParseFromString(fields[FIELD_PRESENCE])
    assert decoded.roster_complete is True
    assert decoded.visitors_present is False
    by_id = {m.member_id: m for m in decoded.members}
    assert set(by_id.keys()) == {"alice", "grandma"}
    assert by_id["alice"].status == household_pb2.PRESENCE_STATUS_AWAY
    assert by_id["grandma"].status == household_pb2.PRESENCE_STATUS_PRESENT_ROOM
    assert by_id["grandma"].room_id == "living_room"

    # Unchanged 10 s later -> suppressed.
    clock.advance(10.0)
    assert await pub.publish_if_due() is False
    assert len(redis.entries) == 1

    # State changes (named guest detected in occupancy) -> publishes immediately.
    clock.advance(5.0)
    occupancy.record_room_presence(
        room_id=1,
        room_name="Living Room",
        ph_id="ph-guest",
        identity_id="guest-bob",
        observed_at=clock.now,
    )
    assert await pub.publish_if_due() is True
    assert len(redis.entries) == 2
    decoded2 = household_pb2.HouseholdPresence()
    decoded2.ParseFromString(redis.entries[-1][1][FIELD_PRESENCE])
    assert decoded2.visitors_present is True

    # Unchanged 60 s later -> heartbeat publishes.
    clock.advance(60.0)
    assert await pub.publish_if_due() is True
    assert len(redis.entries) == 3


@pytest.mark.asyncio
async def test_publisher_fails_closed_when_person_id_is_down(db_factory: Any) -> None:
    db = db_factory()
    try:
        db.add(HouseholdMember(id="grandma", name="Grandma", is_active=True, is_guest=False))
        db.commit()
    finally:
        db.close()

    t0 = datetime.now(UTC)
    clock = _MutableClock(t0)
    redis = _FakeRedis()

    presence_service = AsyncMock()
    presence_service.get.side_effect = lambda pid, at=None: _snapshot(
        pid, PresenceStatus.PRESENT_HOME, at=at or clock.now
    )
    roster_service = AsyncMock()
    roster_service.get_roster_health.side_effect = PersonIDUpstreamError(
        503, "person-id unreachable"
    )

    pub = HouseholdPresencePublisher(
        redis_client=redis,
        presence_service=presence_service,
        roster_health_service=roster_service,
        db_factory=db_factory,
        clock=clock,
    )

    assert await pub.publish_if_due() is True
    decoded = household_pb2.HouseholdPresence()
    decoded.ParseFromString(redis.entries[-1][1][FIELD_PRESENCE])
    assert decoded.roster_complete is False


def test_roster_step_reports_closed_world_activity() -> None:
    roster = _roster_health(is_complete=True, surfaced=0)
    cts_inactive = CTSIdentityReadiness(
        face_evidence_policy="calibrated",
        face_templates_mode="off",
        face_quality_mode="shadow",
        cc_assertion_mode="shadow",
        closed_world_mode="shadow",
        expected_recognizer_version=None,
        expected_quality_version="heuristic-v1",
        reid_gallery_counts=None,
        closed_world=CTSClosedWorldReadiness(
            mode="shadow",
            active=False,
            inactive_reason="roster_incomplete",
            roster_complete=False,
        ),
        cameras=[],
        overlap_group_count=0,
        identities_known=2,
    )
    step_inactive = roster_step(roster, cts=cts_inactive)
    assert (
        "Closed-world prior shaping is inactive (shadow: roster incomplete)."
        in step_inactive.detail
    )

    cts_active = cts_inactive.model_copy(
        update={
            "closed_world": CTSClosedWorldReadiness(
                mode="shadow",
                active=True,
                inactive_reason=None,
                roster_complete=True,
                visitors_present=False,
                presence_age_s=12.0,
            )
        }
    )
    step_active = roster_step(roster, cts=cts_active)
    assert "Closed-world prior shaping is active (shadow)." in step_active.detail
