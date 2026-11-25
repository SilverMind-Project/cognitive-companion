"""Service tests for the device-free position sensor registry and its site-config entry."""

from __future__ import annotations

import pytest
from cts_contracts import PositionSensorModality
from pydantic import ValidationError as PydanticValidationError

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.models.household_settings import HouseholdSettings
from backend.models.room import Room
from backend.schemas.wearables import PositionSensorCreate, PositionSensorUpdate
from backend.services.wearables import (
    PositionSensorRoomIndex,
    PositionSensorService,
    SqlAlchemyWearableRepository,
    WearableSiteConfigService,
)


def _seed_floor_plan(db_factory, *, with_scale: bool = True) -> int:
    with db_factory() as db:
        db.add(
            HouseholdSettings(
                id=1,
                floor_plan_key="floor-plans/test.png",
                floor_plan_width=1000,
                floor_plan_height=800,
                floor_meters_per_pixel=0.01 if with_scale else None,  # 10.0 m x 8.0 m
            )
        )
        room = Room(
            name="Bathroom",
            floor_polygon=[[0.5, 0.5], [0.8, 0.5], [0.8, 0.8], [0.5, 0.8]],
        )
        db.add(room)
        db.commit()
        db.refresh(room)
        return room.id


def _radar(room_id: int, **overrides: object) -> PositionSensorCreate:
    fields: dict[str, object] = {
        "sensor_id": "radar-bathroom-1",
        "label": "Bathroom radar",
        "modality": PositionSensorModality.MMWAVE_RADAR,
        "room_id": room_id,
        "x_norm": 0.5,
        "y_norm": 0.5,
        "yaw_deg": 45.0,
        "calibration_residual_m": 0.08,
    }
    fields.update(overrides)
    return PositionSensorCreate.model_validate(fields)


def test_position_sensor_reaches_site_config_in_metres(db_factory) -> None:
    room_id = _seed_floor_plan(db_factory)
    repo = SqlAlchemyWearableRepository(db_factory)
    sensors = PositionSensorService(repo)
    site = WearableSiteConfigService(repo)
    before = site.build_site_config()

    created = sensors.create_sensor(_radar(room_id), actor="Admin")
    assert created.x_m == pytest.approx(5.0)
    assert created.y_m == pytest.approx(4.0)
    assert created.room_name == "Bathroom"

    cfg = site.build_site_config()
    assert cfg.version != before.version
    [entry] = cfg.position_sensors
    assert entry.sensor_id == "radar-bathroom-1"
    assert entry.room_id == str(room_id)
    assert (entry.x_m, entry.y_m) == (pytest.approx(5.0), pytest.approx(4.0))
    assert entry.yaw_deg == pytest.approx(45.0)
    assert entry.calibration_residual_m == pytest.approx(0.08)
    assert sensors.room_ids_by_source() == {"sensor:radar-bathroom-1": room_id}

    # Inactive sensors leave the site-config (rf-ingress and CTS then drop their tracks).
    sensors.update_sensor(created.id, PositionSensorUpdate(is_active=False), actor="Admin")
    cfg_inactive = site.build_site_config()
    assert cfg_inactive.position_sensors == []
    assert sensors.room_ids_by_source() == {}


def test_household_without_sensors_keeps_its_site_config_version(db_factory) -> None:
    """The version hash covers position sensors only when there are any."""
    _seed_floor_plan(db_factory)
    site = WearableSiteConfigService(SqlAlchemyWearableRepository(db_factory))
    cfg = site.build_site_config()
    assert cfg.position_sensors == []
    assert cfg.version == site.build_site_config().version


def test_position_sensor_requires_floor_plan_scale_and_a_room(db_factory) -> None:
    room_id = _seed_floor_plan(db_factory, with_scale=False)
    sensors = PositionSensorService(SqlAlchemyWearableRepository(db_factory))
    with pytest.raises(ValidationError, match="floor plan"):
        sensors.create_sensor(_radar(room_id), actor="Admin")


def test_position_sensor_room_must_exist_and_cannot_be_cleared(db_factory) -> None:
    room_id = _seed_floor_plan(db_factory)
    sensors = PositionSensorService(SqlAlchemyWearableRepository(db_factory))
    with pytest.raises(NotFoundError):
        sensors.create_sensor(_radar(room_id + 999), actor="Admin")
    created = sensors.create_sensor(_radar(room_id), actor="Admin")
    with pytest.raises(ValidationError, match="must cover a room"):
        sensors.update_sensor(created.id, PositionSensorUpdate(room_id=None), actor="Admin")
    # Clearing the yaw is allowed: a floor-frame gateway needs no pose.
    cleared = sensors.update_sensor(created.id, PositionSensorUpdate(yaw_deg=None), actor="Admin")
    assert cleared.yaw_deg is None
    # Explicit null on other non-nullable columns must return ValidationError (400), never 500.
    for field in ("label", "modality", "x_norm", "y_norm", "calibration_residual_m", "is_active"):
        with pytest.raises(ValidationError, match="cannot be null"):
            sensors.update_sensor(
                created.id,
                PositionSensorUpdate.model_validate({field: None}),
                actor="Admin",
            )


def test_position_sensor_room_index_invalidates_immediately_and_skips_deleted_rooms(
    db_factory,
) -> None:
    room_id = _seed_floor_plan(db_factory)
    repo = SqlAlchemyWearableRepository(db_factory)
    sensors = PositionSensorService(repo)
    index = PositionSensorRoomIndex(sensors, refresh_s=300.0)
    site = WearableSiteConfigService(repo)

    created = sensors.create_sensor(_radar(room_id), actor="Admin")
    assert index.room_for("sensor:radar-bathroom-1") == (room_id, "Bathroom")

    with db_factory() as db:
        bedroom = Room(
            name="Bedroom", floor_polygon=[[0.0, 0.0], [0.4, 0.0], [0.4, 0.4], [0.0, 0.4]]
        )
        db.add(bedroom)
        db.commit()
        db.refresh(bedroom)
        bedroom_id = bedroom.id

    sensors.update_sensor(created.id, PositionSensorUpdate(room_id=bedroom_id), actor="Admin")
    assert index.room_for("sensor:radar-bathroom-1") == (bedroom_id, "Bedroom")

    # Deleting the covered Room nulls room_id (ON DELETE SET NULL); site-config skips orphaned rows.
    with db_factory() as db:
        db.delete(db.get(Room, bedroom_id))
        db.commit()
    index.invalidate()
    assert index.room_for("sensor:radar-bathroom-1") is None
    assert site.build_site_config().position_sensors == []


def test_duplicate_sensor_id_conflicts(db_factory) -> None:
    room_id = _seed_floor_plan(db_factory)
    sensors = PositionSensorService(SqlAlchemyWearableRepository(db_factory))
    sensors.create_sensor(_radar(room_id), actor="Admin")
    with pytest.raises(ConflictError):
        sensors.create_sensor(_radar(room_id, label="Second"), actor="Admin")


@pytest.mark.parametrize(
    "overrides",
    [
        {"sensor_id": "Radar Bathroom"},
        {"sensor_id": "sensor:radar"},
        {"yaw_deg": 180.0},
        {"calibration_residual_m": 0.0},
        {"calibration_residual_m": 1.5},
        {"modality": "sonar"},
    ],
)
def test_position_sensor_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(PydanticValidationError):
        _radar(1, **overrides)
