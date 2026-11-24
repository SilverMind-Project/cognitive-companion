"""Tests for CompanionSurfaceService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from backend.core.exceptions import ValidationError
from backend.models.companion_surface import CompanionSurface
from backend.models.room import Room
from backend.services.companion_surface import CompanionSurfaceService, SurfaceDeviceState


@dataclass(frozen=True)
class _Location:
    room_id: int
    room_name: str = "Kitchen"


class _PersonLocation:
    def __init__(self, location: _Location | None) -> None:
        self.location = location

    async def where_is(self, person_id: str) -> _Location | None:
        return self.location


def _add_room(db_session, name: str) -> Room:
    room = Room(name=name)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    return room


def test_upsert_caregiver_set_room_sets_source_caregiver(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    svc = CompanionSurfaceService(db_factory=db_factory)

    surface = svc.upsert_surface(
        surface_id="kitchen-tablet",
        name="Kitchen Tablet",
        surface_type="movable",
        kind="tablet",
        room_id=room.id,
    )

    assert surface.room_id == room.id
    assert surface.room_source == "caregiver"
    assert surface.room_mismatch is False


def test_surfaces_in_room_returns_enabled_only(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    svc = CompanionSurfaceService(db_factory=db_factory)
    svc.upsert_surface(
        surface_id="enabled",
        name="Enabled",
        surface_type="fixed",
        kind="display",
        room_id=room.id,
        is_enabled=True,
    )
    svc.upsert_surface(
        surface_id="disabled",
        name="Disabled",
        surface_type="fixed",
        kind="display",
        room_id=room.id,
        is_enabled=False,
    )

    surfaces = svc.surfaces_in_room(room.id)

    assert [s.id for s in surfaces] == ["enabled"]


def test_record_heartbeat_updates_last_seen(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    svc = CompanionSurfaceService(db_factory=db_factory, time_fn=lambda: now)
    svc.upsert_surface(
        surface_id="tablet",
        name="Tablet",
        surface_type="movable",
        kind="tablet",
        room_id=room.id,
    )

    svc.record_heartbeat("tablet", reported_room_id=room.id)

    stored = db_session.get(CompanionSurface, "tablet")
    assert stored.last_seen_at == now


@pytest.mark.asyncio
async def test_cross_check_agreeing_room_clears_mismatch(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    svc = CompanionSurfaceService(
        db_factory=db_factory,
        person_location_service=_PersonLocation(_Location(room_id=room.id)),
    )
    svc.upsert_surface(
        surface_id="tablet",
        name="Tablet",
        surface_type="movable",
        kind="tablet",
        room_id=room.id,
    )
    db_session.get(CompanionSurface, "tablet").room_mismatch = True
    db_session.commit()

    await svc.cross_check_room("tablet", "person-1")

    assert db_session.get(CompanionSurface, "tablet").room_mismatch is False


@pytest.mark.asyncio
async def test_cross_check_disagreeing_room_sets_mismatch_does_not_overwrite_caregiver(
    db_factory, db_session
):
    kitchen = _add_room(db_session, "Kitchen")
    living = _add_room(db_session, "Living")
    svc = CompanionSurfaceService(
        db_factory=db_factory,
        person_location_service=_PersonLocation(_Location(room_id=living.id)),
    )
    svc.upsert_surface(
        surface_id="tablet",
        name="Tablet",
        surface_type="movable",
        kind="tablet",
        room_id=kitchen.id,
    )

    await svc.cross_check_room("tablet", "person-1")

    stored = db_session.get(CompanionSurface, "tablet")
    assert stored.room_id == kitchen.id
    assert stored.room_source == "caregiver"
    assert stored.room_mismatch is True


@pytest.mark.asyncio
async def test_cross_check_movable_without_caregiver_room_adopts_inferred(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    db_session.add(
        CompanionSurface(
            id="tablet",
            name="Tablet",
            surface_type="movable",
            room_id=None,
            room_source="cts_inferred",
            kind="tablet",
            is_enabled=True,
            room_mismatch=False,
        )
    )
    db_session.commit()
    svc = CompanionSurfaceService(
        db_factory=db_factory,
        person_location_service=_PersonLocation(_Location(room_id=room.id)),
    )

    await svc.cross_check_room("tablet", "person-1")

    stored = db_session.get(CompanionSurface, "tablet")
    assert stored.room_id == room.id
    assert stored.room_source == "cts_inferred"
    assert stored.room_mismatch is False


@pytest.mark.asyncio
async def test_missing_person_location_is_graceful(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    svc = CompanionSurfaceService(db_factory=db_factory, person_location_service=None)
    svc.upsert_surface(
        surface_id="tablet",
        name="Tablet",
        surface_type="movable",
        kind="tablet",
        room_id=room.id,
    )

    await svc.cross_check_room("tablet", "person-1")

    assert db_session.get(CompanionSurface, "tablet").room_mismatch is False


def test_create_and_heartbeat_tv_surface_with_hardware_telemetry(db_factory, db_session):
    room = _add_room(db_session, "Living Room")
    svc = CompanionSurfaceService(db_factory=db_factory)
    svc.upsert_surface(
        surface_id="living-tv",
        name="Living Room TV",
        surface_type="fixed",
        kind="tv",
        room_id=room.id,
    )

    svc.record_heartbeat(
        "living-tv",
        reported_room_id=room.id,
        device=SurfaceDeviceState(
            platform="android_tv", mic_active=True, camera_active=False, screen_awake=True
        ),
    )

    surface = svc.get_surface("living-tv")
    assert surface is not None
    assert surface.kind == "tv"
    assert surface.platform == "android_tv"
    assert (surface.mic_active, surface.camera_active, surface.screen_awake) == (True, False, True)


def test_a_browser_heartbeat_keeps_the_device_state_the_shell_reported(db_factory, db_session):
    """A field a heartbeat does not report keeps its last value, so a plain browser
    heartbeat never hides that the native shell's microphone is on."""
    svc = CompanionSurfaceService(db_factory=db_factory)
    svc.upsert_surface(
        surface_id="kitchen-tablet",
        name="Kitchen",
        surface_type="fixed",
        kind="tablet",
        room_id=None,
    )
    svc.record_heartbeat(
        "kitchen-tablet",
        reported_room_id=None,
        device=SurfaceDeviceState(platform="android_tablet", mic_active=True),
    )

    svc.record_heartbeat("kitchen-tablet", reported_room_id=None)
    svc.record_heartbeat("kitchen-tablet", reported_room_id=None, device=SurfaceDeviceState())

    surface = svc.get_surface("kitchen-tablet")
    assert surface is not None
    assert (surface.platform, surface.mic_active) == ("android_tablet", True)


def test_unknown_kind_is_rejected(db_factory):
    svc = CompanionSurfaceService(db_factory=db_factory)

    with pytest.raises(ValidationError, match="tv"):
        svc.upsert_surface(
            surface_id="x", name="X", surface_type="fixed", kind="projector", room_id=None
        )


@pytest.mark.asyncio
async def test_surface_for_person_is_the_enabled_surface_in_her_room(db_factory, db_session):
    kitchen = _add_room(db_session, "Kitchen")
    bedroom = _add_room(db_session, "Bedroom")
    svc = CompanionSurfaceService(
        db_factory=db_factory, person_location_service=_PersonLocation(_Location(kitchen.id))
    )
    svc.upsert_surface(
        surface_id="b-kitchen-off",
        name="B kitchen (off)",
        surface_type="fixed",
        kind="tablet",
        room_id=kitchen.id,
        is_enabled=False,
    )
    svc.upsert_surface(
        surface_id="kitchen-tablet",
        name="Kitchen",
        surface_type="fixed",
        kind="tablet",
        room_id=kitchen.id,
    )
    svc.upsert_surface(
        surface_id="bedroom-tablet",
        name="A bedroom",
        surface_type="fixed",
        kind="tablet",
        room_id=bedroom.id,
    )

    assert await svc.surface_for_person("resident-1") == "kitchen-tablet"


@pytest.mark.asyncio
@pytest.mark.parametrize("location", [None, _Location(room_id=999_999)])
async def test_surface_for_person_is_none_without_a_room_surface(db_factory, location):
    svc = CompanionSurfaceService(
        db_factory=db_factory, person_location_service=_PersonLocation(location)
    )

    assert await svc.surface_for_person("resident-1") is None
    assert await svc.surface_for_person(None) is None
