"""M38 Part F: PersonTrackingService's SSOT bridge writes.

Covers the two new write paths added by M38:

1. Part D -- ``process_camera_event`` calls ``RecameraLocationIngest``
   alongside its legacy ``PersonSighting``/``PersonLocationState`` writes
   (the deliberate double-write bridge; legacy writes are unchanged here).
2. Part E -- ``_correlate_presence_sensor`` discovers candidates from the
   SSOT (``recent_observations``), re-expresses the already-in-room /
   fresh-elsewhere skip checks against ``where_is``/``latest_observation``,
   and additionally writes through ``ingest_observation(source="sensor")``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.integrations.person_id_client import BatchIdentifyResult, FaceResult
from backend.models.person import HouseholdMember, PersonSighting
from backend.models.room import Room
from backend.models.sensor import Sensor
from backend.services.cts.source_authority import SourceAuthority
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.recamera_ingest import RecameraLocationIngest
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_tracking import PersonTrackingService


def _make_location_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


class _FakePersonIDDisabled:
    enabled = False


class _FakePersonIDEnabled:
    enabled = True

    def __init__(self, faces: list[FaceResult]) -> None:
        self._faces = faces

    async def identify_batch(self, images_b64, **_kwargs) -> BatchIdentifyResult:
        return BatchIdentifyResult(frames=[self._faces], motion=[])


class _FakeHA:
    def __init__(self, state: str = "off") -> None:
        self._state = state

    async def get_entity_state(self, _entity_id: str) -> dict:
        return {"state": self._state}

    async def set_person_location(self, *_args, **_kwargs) -> None:
        return None


def _seed_household(db_factory, room_names: dict[int, str], person_id: str = "alice") -> None:
    db = db_factory()
    try:
        db.add(HouseholdMember(id=person_id, name="Alice"))
        for room_id, name in room_names.items():
            db.add(Room(id=room_id, name=name))
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_process_camera_event_writes_legacy_and_ssot_alongside(db_factory):
    """The double-write bridge (Part D.2): one detection produces both the
    unchanged legacy PersonSighting row and an SSOT segment."""
    _seed_household(db_factory, {1: "kitchen"})
    location_service = _make_location_service()
    recamera_ingest = RecameraLocationIngest(
        db_factory=db_factory,
        location_service=location_service,
        assertion_publisher=None,
        publish_assertions=False,
    )
    face = FaceResult(person_id="alice", name="Alice", confidence=0.9, bbox=[0, 0, 10, 10])
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDEnabled([face]),
        ha_client=_FakeHA(),
        authority=SourceAuthority(),
        recamera_ingest=recamera_ingest,
        person_location_service=location_service,
    )

    with patch.object(
        PersonTrackingService, "_load_images_as_base64", AsyncMock(return_value=["fakeb64"])
    ):
        result = await svc.process_camera_event(
            sensor_id="cam-1",
            media_paths=["irrelevant.jpg"],
            room_name="kitchen",
        )

    assert len(result.detections) == 1

    db = db_factory()
    try:
        sightings = db.query(PersonSighting).filter(PersonSighting.person_id == "alice").all()
        assert len(sightings) == 1
        assert sightings[0].source == "camera"
    finally:
        db.close()

    loc = await location_service.where_is("alice")
    assert loc is not None
    assert loc.room_id == 1


@pytest.mark.asyncio
async def test_process_camera_event_without_recamera_ingest_still_writes_legacy(db_factory):
    """recamera_ingest is optional (graceful degradation, not a hidden
    default): legacy writes must keep working when it's None."""
    _seed_household(db_factory, {1: "kitchen"})
    face = FaceResult(person_id="alice", name="Alice", confidence=0.9, bbox=[0, 0, 10, 10])
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDEnabled([face]),
        ha_client=_FakeHA(),
        authority=SourceAuthority(),
    )

    with patch.object(
        PersonTrackingService, "_load_images_as_base64", AsyncMock(return_value=["fakeb64"])
    ):
        result = await svc.process_camera_event(
            sensor_id="cam-1",
            media_paths=["irrelevant.jpg"],
            room_name="kitchen",
        )

    assert len(result.detections) == 1
    db = db_factory()
    try:
        assert db.query(PersonSighting).filter(PersonSighting.person_id == "alice").count() == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ha_correlation_candidate_from_ssot_writes_legacy_and_ssot(db_factory):
    """Part E: a person recently seen by camera (SSOT candidate discovery),
    now stale in their old room, gets HA-correlated to the sensor's room --
    both the legacy tables and the SSOT are written."""
    location_service = _make_location_service()
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDDisabled(),
        ha_client=_FakeHA(state="on"),
        authority=SourceAuthority(),
        person_location_service=location_service,
    )

    db = db_factory()
    try:
        db.add(HouseholdMember(id="alice", name="Alice"))
        db.add(Room(id=1, name="Kitchen"))
        db.add(Room(id=2, name="Living Room"))
        sensor = Sensor(
            id="presence-1",
            name="Living Room Presence",
            room_id=2,
            sensor_type="presence",
            source="homeassistant",
            enabled=True,
        )
        db.add(sensor)
        db.commit()
        db.refresh(sensor)
    finally:
        db.close()

    # Alice was last seen by camera in the kitchen 5 minutes ago -- inside
    # the 10-minute candidate window, but well past the 60s freshness guard,
    # so correlation to a different room (living room) should proceed.
    stale_sighting_time = datetime.now(UTC) - timedelta(minutes=5)
    await location_service.ingest_observation(
        person_id="alice",
        observed_at=stale_sighting_time,
        source="world_tracker",
        room_id=1,
        confidence=0.9,
    )

    db = db_factory()
    try:
        # Re-fetch: `sensor` is bound to the (now-closed) setup session, and
        # `_correlate_presence_sensor` lazy-loads `sensor.room`.
        live_sensor = db.get(Sensor, sensor.id)
        await svc._correlate_presence_sensor(live_sensor, db)
    finally:
        db.close()

    db = db_factory()
    try:
        sightings = (
            db.query(PersonSighting)
            .filter(PersonSighting.person_id == "alice", PersonSighting.source == "ha_sensor")
            .all()
        )
        assert len(sightings) == 1
    finally:
        db.close()

    loc = await location_service.where_is("alice")
    assert loc is not None
    assert loc.room_id == 2


@pytest.mark.asyncio
async def test_ha_correlation_skips_when_already_in_target_room(db_factory):
    """already-in-room skip check, re-expressed against where_is()."""
    location_service = _make_location_service()
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDDisabled(),
        ha_client=_FakeHA(state="on"),
        authority=SourceAuthority(),
        person_location_service=location_service,
    )

    db = db_factory()
    try:
        db.add(HouseholdMember(id="bob", name="Bob"))
        db.add(Room(id=2, name="Living Room"))
        sensor = Sensor(
            id="presence-2",
            name="Living Room Presence",
            room_id=2,
            sensor_type="presence",
            source="homeassistant",
            enabled=True,
        )
        db.add(sensor)
        db.commit()
        db.refresh(sensor)
    finally:
        db.close()

    await location_service.ingest_observation(
        person_id="bob",
        observed_at=datetime.now(UTC) - timedelta(minutes=2),
        source="recamera_vlm",
        room_id=2,
        confidence=0.8,
    )

    db = db_factory()
    try:
        # Re-fetch: `sensor` is bound to the (now-closed) setup session, and
        # `_correlate_presence_sensor` lazy-loads `sensor.room`.
        live_sensor = db.get(Sensor, sensor.id)
        await svc._correlate_presence_sensor(live_sensor, db)
    finally:
        db.close()

    db = db_factory()
    try:
        assert (
            db.query(PersonSighting)
            .filter(PersonSighting.person_id == "bob", PersonSighting.source == "ha_sensor")
            .count()
            == 0
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ha_correlation_skips_when_fresh_elsewhere(db_factory):
    """fresh-elsewhere skip check, re-expressed against latest_observation()."""
    location_service = _make_location_service()
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDDisabled(),
        ha_client=_FakeHA(state="on"),
        authority=SourceAuthority(),
        person_location_service=location_service,
    )

    db = db_factory()
    try:
        db.add(HouseholdMember(id="carol", name="Carol"))
        db.add(Room(id=1, name="Kitchen"))
        db.add(Room(id=2, name="Living Room"))
        sensor = Sensor(
            id="presence-3",
            name="Living Room Presence",
            room_id=2,
            sensor_type="presence",
            source="homeassistant",
            enabled=True,
        )
        db.add(sensor)
        db.commit()
        db.refresh(sensor)
    finally:
        db.close()

    # Carol was seen in the kitchen only 10 seconds ago: fresh elsewhere,
    # must not be overridden by this HA correlation cycle.
    await location_service.ingest_observation(
        person_id="carol",
        observed_at=datetime.now(UTC) - timedelta(seconds=10),
        source="world_tracker",
        room_id=1,
        confidence=0.9,
    )

    db = db_factory()
    try:
        # Re-fetch: `sensor` is bound to the (now-closed) setup session, and
        # `_correlate_presence_sensor` lazy-loads `sensor.room`.
        live_sensor = db.get(Sensor, sensor.id)
        await svc._correlate_presence_sensor(live_sensor, db)
    finally:
        db.close()

    loc = await location_service.where_is("carol")
    assert loc is not None
    assert loc.room_id == 1  # unchanged

    db = db_factory()
    try:
        assert (
            db.query(PersonSighting)
            .filter(PersonSighting.person_id == "carol", PersonSighting.source == "ha_sensor")
            .count()
            == 0
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ha_correlation_skips_unknown_bucket_candidate(db_factory):
    """W7 regression: the unknown bucket must never gain a segment via HA
    correlation either. A reCamera-ingested ``unknown_*`` observation is a
    valid recent_observations() candidate, but correlating it to a room
    would open a segment shared by every unidentified visitor in the house
    -- the exact churn W7 exists to prevent on the reCamera ingest path."""
    location_service = _make_location_service()
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDDisabled(),
        ha_client=_FakeHA(state="on"),
        authority=SourceAuthority(),
        person_location_service=location_service,
    )

    db = db_factory()
    try:
        db.add(Room(id=2, name="Living Room"))
        sensor = Sensor(
            id="presence-6",
            name="Living Room Presence",
            room_id=2,
            sensor_type="presence",
            source="homeassistant",
            enabled=True,
        )
        db.add(sensor)
        db.commit()
        db.refresh(sensor)
    finally:
        db.close()

    await location_service.ingest_observation(
        person_id="unknown_7",
        observed_at=datetime.now(UTC) - timedelta(minutes=2),
        source="recamera_vlm",
        room_id=1,
        confidence=0.5,
        skip_segment=True,
    )

    db = db_factory()
    try:
        live_sensor = db.get(Sensor, sensor.id)
        await svc._correlate_presence_sensor(live_sensor, db)
    finally:
        db.close()

    assert (await location_service.where_is("unknown_7")) is None
    db = db_factory()
    try:
        assert (
            db.query(PersonSighting)
            .filter(PersonSighting.person_id == "unknown_7", PersonSighting.source == "ha_sensor")
            .count()
            == 0
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ha_correlation_noop_when_sensor_state_off(db_factory):
    location_service = _make_location_service()
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDDisabled(),
        ha_client=_FakeHA(state="off"),
        authority=SourceAuthority(),
        person_location_service=location_service,
    )
    db = db_factory()
    try:
        sensor = Sensor(
            id="presence-4",
            name="Sensor",
            room_id=None,
            sensor_type="presence",
            source="homeassistant",
            enabled=True,
        )
        db.add(sensor)
        db.commit()
        db.refresh(sensor)
        await svc._correlate_presence_sensor(sensor, db)
    finally:
        db.close()

    assert (await location_service.where_is("alice")) is None


@pytest.mark.asyncio
async def test_ha_correlation_noop_without_location_service(db_factory):
    """person_location_service is optional (graceful degradation): no
    location service means correlation cannot run, but must not raise."""
    svc = PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonIDDisabled(),
        ha_client=_FakeHA(state="on"),
        authority=SourceAuthority(),
    )
    db = db_factory()
    try:
        sensor = Sensor(
            id="presence-5",
            name="Sensor",
            room_id=None,
            sensor_type="presence",
            source="homeassistant",
            enabled=True,
        )
        db.add(sensor)
        db.commit()
        db.refresh(sensor)
        await svc._correlate_presence_sensor(sensor, db)  # must not raise
    finally:
        db.close()
