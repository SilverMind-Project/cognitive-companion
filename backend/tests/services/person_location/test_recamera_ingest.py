"""M38 Part F: FaceSightingIngest adapter tests.

Detection -> observation row + gated assertion publish, guest
auto-provisioning, missing-room degradation, and the unknown-bucket rule
(observation only, no segment, no assertion).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.models.sensor import Sensor
from backend.services.cts.identity_assertion_publisher import IdentityAssertionPublisher
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.face_sighting_ingest import FaceSightingIngest
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService


def _make_location_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


def _seed_room_and_sensor(
    db_factory, *, sensor_id: str = "cam-1", room_id: int = 1, room_name: str = "kitchen"
) -> None:
    db = db_factory()
    try:
        db.add(Room(id=room_id, name=room_name))
        db.add(Sensor(id=sensor_id, name=sensor_id, room_id=room_id, sensor_type="camera"))
        db.commit()
    finally:
        db.close()


def _make_adapter(
    db_factory,
    *,
    publisher: IdentityAssertionPublisher | None = None,
    publish_assertions: bool = True,
    location_service: PersonLocationService | None = None,
    occupancy_read_model=None,
) -> tuple[FaceSightingIngest, PersonLocationService]:
    svc = location_service or _make_location_service()
    adapter = FaceSightingIngest(
        db_factory=db_factory,
        location_service=svc,
        assertion_publisher=publisher,
        publish_assertions=publish_assertions,
        occupancy_read_model=occupancy_read_model,
    )
    return adapter, svc


@pytest.mark.asyncio
async def test_confirmed_detection_writes_observation_and_publishes_assertion(db_factory):
    _seed_room_and_sensor(db_factory)
    redis_mock = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)
    adapter, svc = _make_adapter(db_factory, publisher=publisher, publish_assertions=True)

    db = db_factory()
    try:
        db.add(HouseholdMember(id="alice", name="Alice"))
        db.commit()
    finally:
        db.close()

    await adapter.ingest(
        person_id="alice",
        sensor_id="cam-1",
        room_name="kitchen",
        confidence=0.85,
        raw_similarity=0.9,
    )

    loc = await svc.where_is("alice")
    assert loc is not None
    assert loc.room_id == 1

    redis_mock.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_publish_disabled_flag_suppresses_assertion_even_with_publisher(db_factory):
    _seed_room_and_sensor(db_factory)
    redis_mock = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)
    adapter, svc = _make_adapter(db_factory, publisher=publisher, publish_assertions=False)

    db = db_factory()
    try:
        db.add(HouseholdMember(id="bob", name="Bob"))
        db.commit()
    finally:
        db.close()

    await adapter.ingest(person_id="bob", sensor_id="cam-1", room_name="kitchen", confidence=0.8)

    assert (await svc.where_is("bob")) is not None
    redis_mock.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_no_publisher_configured_never_raises(db_factory):
    """A reCamera-only deployment with no Redis configured must still ingest."""
    _seed_room_and_sensor(db_factory)
    adapter, svc = _make_adapter(db_factory, publisher=None, publish_assertions=True)

    db = db_factory()
    try:
        db.add(HouseholdMember(id="carol", name="Carol"))
        db.commit()
    finally:
        db.close()

    await adapter.ingest(person_id="carol", sensor_id="cam-1", room_name="kitchen", confidence=0.8)

    assert (await svc.where_is("carol")) is not None


@pytest.mark.asyncio
async def test_guest_member_auto_provisioned(db_factory):
    """The unknown bucket auto-provisions a guest HouseholdMember so the
    SSOT FK cannot fail (X16), mirroring legacy _record_sighting."""
    _seed_room_and_sensor(db_factory)
    adapter, _svc = _make_adapter(db_factory)

    await adapter.ingest(
        person_id="unknown_42", sensor_id="cam-1", room_name="kitchen", confidence=0.6
    )

    db = db_factory()
    try:
        member = db.get(HouseholdMember, "unknown_42")
        assert member is not None
        assert member.is_guest is True
        assert member.name == "Guest"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_unknown_bucket_gets_observation_but_no_segment_or_assertion(db_factory):
    """The literal unidentified bucket is a merged pseudo-person: audit
    parity (observation row) but no segment and no identity assertion."""
    _seed_room_and_sensor(db_factory)
    redis_mock = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)
    adapter, svc = _make_adapter(db_factory, publisher=publisher, publish_assertions=True)

    await adapter.ingest(
        person_id="unknown", sensor_id="cam-1", room_name="kitchen", confidence=0.6
    )

    # No segment for the merged pseudo-person.
    assert (await svc.where_is("unknown")) is None
    # No assertion published for it either.
    redis_mock.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_named_guest_gets_full_treatment(db_factory):
    """A real (non-"unknown"-prefixed) guest member id, already enrolled,
    gets segments and assertions like any other identity."""
    _seed_room_and_sensor(db_factory)
    db = db_factory()
    try:
        db.add(HouseholdMember(id="guest-visitor-1", name="Visiting Nephew", is_guest=True))
        db.commit()
    finally:
        db.close()

    redis_mock = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)
    adapter, svc = _make_adapter(db_factory, publisher=publisher, publish_assertions=True)

    await adapter.ingest(
        person_id="guest-visitor-1", sensor_id="cam-1", room_name="kitchen", confidence=0.75
    )

    assert (await svc.where_is("guest-visitor-1")) is not None
    redis_mock.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_room_resolution_falls_back_to_room_name_when_sensor_unbound(db_factory):
    """Sensor.room wins when present; Room.name lookup only when the sensor
    has no room binding."""
    db = db_factory()
    try:
        db.add(Room(id=9, name="garage"))
        db.add(Sensor(id="cam-unbound", name="cam-unbound", room_id=None, sensor_type="camera"))
        db.add(HouseholdMember(id="dave", name="Dave"))
        db.commit()
    finally:
        db.close()

    adapter, svc = _make_adapter(db_factory)

    await adapter.ingest(
        person_id="dave", sensor_id="cam-unbound", room_name="garage", confidence=0.7
    )

    loc = await svc.where_is("dave")
    assert loc is not None
    assert loc.room_id == 9


@pytest.mark.asyncio
async def test_unresolvable_room_still_records_observation_with_room_id_none(db_factory):
    """Neither Sensor.room nor a matching Room.name: observation is still
    recorded (room_id=None), just without a segment effect."""
    db = db_factory()
    try:
        db.add(Sensor(id="cam-orphan", name="cam-orphan", room_id=None, sensor_type="camera"))
        db.add(HouseholdMember(id="erin", name="Erin"))
        db.commit()
    finally:
        db.close()

    adapter, svc = _make_adapter(db_factory)

    await adapter.ingest(
        person_id="erin", sensor_id="cam-orphan", room_name="nonexistent_room", confidence=0.7
    )

    # No segment (room unresolved)...
    assert (await svc.where_is("erin")) is None
    # ...but the observation row exists (full-fidelity audit).
    recent = await svc.recent_observations(since=datetime(2020, 1, 1, tzinfo=UTC))
    assert any(o.person_id == "erin" for o in recent)


@pytest.mark.asyncio
async def test_published_assertion_carries_room_and_calibration_no_coordinates(db_factory):
    """Identity-continuity M09: the published assertion carries room_name,
    yaw_deg, and calibration fields, but never floor coordinates (reCameras
    have no spatial calibration on either side)."""
    from backend.integrations.proto.continuoustracking.v1.tracking_pb2 import (
        CCIdentityAssertion,
    )

    _seed_room_and_sensor(db_factory)
    redis_mock = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)
    adapter, _svc = _make_adapter(db_factory, publisher=publisher, publish_assertions=True)

    db = db_factory()
    try:
        db.add(HouseholdMember(id="ivy", name="Ivy"))
        db.commit()
    finally:
        db.close()

    await adapter.ingest(
        person_id="ivy",
        sensor_id="cam-1",
        room_name="kitchen",
        confidence=0.85,
        raw_similarity=0.9,
        calibrated_confidence=0.91,
        calibration_status="ready",
        yaw_deg=8.0,
    )

    redis_mock.xadd.assert_called_once()
    fields = redis_mock.xadd.call_args[0][1]
    msg = CCIdentityAssertion.FromString(fields[b"assertion"])
    assert msg.room_name == "kitchen"
    assert msg.calibration_status == "ready"
    assert msg.HasField("calibrated_confidence")
    assert msg.calibrated_confidence == pytest.approx(0.91, abs=1e-4)
    assert msg.has_yaw is True
    assert msg.yaw_deg == pytest.approx(8.0, abs=1e-4)
    assert msg.has_floor_point is False
    assert msg.source == "cc-face-sighting"


@pytest.mark.asyncio
async def test_adapter_never_writes_a_floor_point(db_factory):
    """CC-M28 rule (carried into every ingestion path, M38 Part D.4):
    reCamera detections carry no floor coordinates -- never fabricate one."""
    _seed_room_and_sensor(db_factory)
    adapter, svc = _make_adapter(db_factory)

    db = db_factory()
    try:
        db.add(HouseholdMember(id="frank", name="Frank"))
        db.commit()
    finally:
        db.close()

    await adapter.ingest(person_id="frank", sensor_id="cam-1", room_name="kitchen", confidence=0.8)

    assert await svc.latest_floor_point("frank", max_age_s=10**9) is None


@pytest.mark.asyncio
async def test_adapter_records_occupancy_for_identified_person(db_factory):
    """M39 Part C: FaceSightingIngest records occupancy for identified persons into OccupancyReadModel."""
    from backend.services.occupancy.read_model import OccupancyReadModel

    _seed_room_and_sensor(db_factory)
    occupancy_rm = OccupancyReadModel()
    adapter, _svc = _make_adapter(db_factory, occupancy_read_model=occupancy_rm)

    db = db_factory()
    try:
        db.add(HouseholdMember(id="grace", name="Grace"))
        db.commit()
    finally:
        db.close()

    await adapter.ingest(person_id="grace", sensor_id="cam-1", room_name="kitchen", confidence=0.85)

    occupancy = await occupancy_rm.get_occupancy()
    assert len(occupancy) == 1
    assert occupancy[0].room_name == "kitchen"
    assert occupancy[0].person_ids == ["grace"]
    assert occupancy[0].source == "face_sighting"


@pytest.mark.asyncio
async def test_adapter_includes_transition_metadata(db_factory):
    """M39 Part D: FaceSightingIngest includes transition metadata on observation."""
    from backend.services.camera_topology import RoomTransition

    _seed_room_and_sensor(db_factory)
    adapter, svc = _make_adapter(db_factory)

    db = db_factory()
    try:
        db.add(HouseholdMember(id="henry", name="Henry"))
        db.commit()
    finally:
        db.close()

    transition = RoomTransition(
        person_id="henry",
        person_name="Henry",
        sensor_id="cam-1",
        direction_raw="left_to_right",
        semantic="entered_room",
        from_room_id=2,
        from_room_name="bedroom",
        to_room_id=1,
        to_room_name="kitchen",
        confidence=0.85,
    )

    await adapter.ingest(
        person_id="henry",
        sensor_id="cam-1",
        room_name="kitchen",
        confidence=0.85,
        transition=transition,
    )

    obs = await svc.latest_observation("henry")
    assert obs is not None
    assert obs.metadata.get("from_room") == "bedroom"
    assert obs.metadata.get("direction") == "entered_room"
