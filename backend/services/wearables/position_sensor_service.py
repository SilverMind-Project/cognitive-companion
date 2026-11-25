"""Registry of device-free position sensors (mmWave radar and room LiDAR).

A position sensor publishes anonymous floor-plane tracks and never identity. The
registry is the allowlist rf-ingress and CTS read through the site-config: a track from a
sensor that is not registered and active is dropped. Each sensor covers one room, which
Cognitive Companion uses to place a tracked person, and carries its mounting pose and its
systematic calibration residual.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from cts_contracts import PositionSensorModality, source_id_for_sensor
from sqlalchemy.exc import IntegrityError

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.wearable import PositionSensor
from backend.schemas.wearables import (
    PositionSensorCreate,
    PositionSensorListOut,
    PositionSensorOut,
    PositionSensorUpdate,
)
from backend.services.floor_plan_geometry import FloorPlanScale, floor_plan_scale, norm_to_floor_m
from backend.services.wearables.repositories import SqlAlchemyWearableRepository

logger = get_logger(__name__)


def _sensor_out(
    sensor: PositionSensor,
    *,
    scale: FloorPlanScale | None,
    room_names: dict[int, str],
) -> PositionSensorOut:
    x_m: float | None = None
    y_m: float | None = None
    if scale is not None:
        raw_x, raw_y = norm_to_floor_m(sensor.x_norm, sensor.y_norm, scale)
        x_m = round(raw_x, 4)
        y_m = round(raw_y, 4)
    return PositionSensorOut(
        id=sensor.id,
        sensor_id=sensor.sensor_id,
        label=sensor.label,
        modality=PositionSensorModality(sensor.modality),
        room_id=sensor.room_id,
        room_name=room_names.get(sensor.room_id) if sensor.room_id is not None else None,
        x_norm=sensor.x_norm,
        y_norm=sensor.y_norm,
        x_m=x_m,
        y_m=y_m,
        yaw_deg=sensor.yaw_deg,
        calibration_residual_m=sensor.calibration_residual_m,
        is_active=sensor.is_active,
        created_at=sensor.created_at,
        updated_at=sensor.updated_at,
    )


class PositionSensorService:
    """CRUD for registered position sensors on the household floor plan."""

    _NON_NULL_FIELDS = frozenset(
        {"label", "modality", "room_id", "x_norm", "y_norm", "calibration_residual_m", "is_active"}
    )

    def __init__(
        self,
        repo: SqlAlchemyWearableRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._on_change: list[Callable[[], None]] = []

    def register_on_change(self, callback: Callable[[], None]) -> None:
        """Register a listener notified after sensor creates, updates, or deletes commit."""
        self._on_change.append(callback)

    def _notify_changed(self) -> None:
        for callback in self._on_change:
            callback()

    def list_sensors(self, *, active_only: bool = False) -> PositionSensorListOut:
        with self._repo.session() as db:
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            items = [
                _sensor_out(s, scale=scale, room_names=room_names)
                for s in self._repo.list_position_sensors(db, active_only=active_only)
            ]
            return PositionSensorListOut(
                items=items, total=len(items), floor_plan_ready=scale is not None
            )

    def get_sensor(self, sensor_uuid: uuid.UUID) -> PositionSensorOut:
        with self._repo.session() as db:
            sensor = self._repo.get_position_sensor(db, sensor_uuid)
            if sensor is None:
                raise NotFoundError("PositionSensor", str(sensor_uuid))
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            return _sensor_out(sensor, scale=scale, room_names=room_names)

    def create_sensor(self, payload: PositionSensorCreate, *, actor: str) -> PositionSensorOut:
        now = self._clock()
        with self._repo.session() as db:
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            if scale is None:
                raise ValidationError(
                    "Upload a household floor plan and set its measured scale before "
                    "placing position sensors"
                )
            if self._repo.get_room(db, payload.room_id) is None:
                raise NotFoundError("Room", payload.room_id)
            sensor = PositionSensor(
                id=uuid.uuid4(),
                sensor_id=payload.sensor_id,
                label=payload.label,
                modality=payload.modality.value,
                room_id=payload.room_id,
                x_norm=payload.x_norm,
                y_norm=payload.y_norm,
                yaw_deg=payload.yaw_deg,
                calibration_residual_m=payload.calibration_residual_m,
                is_active=payload.is_active,
                created_at=now,
                updated_at=now,
            )
            db.add(sensor)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError("A position sensor with that sensor_id already exists") from exc
            db.refresh(sensor)
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            logger.info(
                "position_sensor_created",
                sensor_id=sensor.sensor_id,
                modality=sensor.modality,
                actor=actor,
            )
            out = _sensor_out(sensor, scale=scale, room_names=room_names)
        self._notify_changed()
        return out

    def update_sensor(
        self,
        sensor_uuid: uuid.UUID,
        payload: PositionSensorUpdate,
        *,
        actor: str,
    ) -> PositionSensorOut:
        now = self._clock()
        with self._repo.session() as db:
            sensor = self._repo.get_position_sensor(db, sensor_uuid)
            if sensor is None:
                raise NotFoundError("PositionSensor", str(sensor_uuid))
            updates = payload.model_dump(exclude_unset=True)
            if "room_id" in updates:
                room_id = updates["room_id"]
                # A sensor without a room cannot place anyone, so the room is never cleared.
                if room_id is None:
                    raise ValidationError("A position sensor must cover a room")
                if self._repo.get_room(db, room_id) is None:
                    raise NotFoundError("Room", room_id)
            for key in self._NON_NULL_FIELDS:
                if key in updates and updates[key] is None:
                    raise ValidationError(f"{key} cannot be null")
            for key, value in updates.items():
                if isinstance(value, PositionSensorModality):
                    setattr(sensor, key, value.value)
                else:
                    setattr(sensor, key, value)
            sensor.updated_at = now
            db.commit()
            db.refresh(sensor)
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            logger.info(
                "position_sensor_updated",
                sensor_id=sensor.sensor_id,
                is_active=sensor.is_active,
                actor=actor,
            )
            out = _sensor_out(sensor, scale=scale, room_names=room_names)
        self._notify_changed()
        return out

    def delete_sensor(self, sensor_uuid: uuid.UUID, *, actor: str) -> None:
        with self._repo.session() as db:
            sensor = self._repo.get_position_sensor(db, sensor_uuid)
            if sensor is None:
                raise NotFoundError("PositionSensor", str(sensor_uuid))
            sensor_id = sensor.sensor_id
            db.delete(sensor)
            db.commit()
            logger.info("position_sensor_deleted", sensor_id=sensor_id, actor=actor)
        self._notify_changed()

    def rooms_by_source(self) -> dict[str, tuple[int, str]]:
        """Map each active sensor's source id (``sensor:<id>``) to ``(room_id, room_name)``."""
        with self._repo.session() as db:
            rooms = self._repo.list_rooms_map(db)
            return {
                source_id_for_sensor(s.sensor_id): (s.room_id, rooms[s.room_id].name)
                for s in self._repo.list_position_sensors(db, active_only=True)
                if s.room_id is not None and s.room_id in rooms
            }

    def room_ids_by_source(self) -> dict[str, int]:
        """Map each active sensor's source id (``sensor:<id>``) to the room it covers."""
        return {src: rid for src, (rid, _name) in self.rooms_by_source().items()}


class PositionSensorRoomIndex:
    """Cached map from a position sensor's source id to the room it covers.

    Tracking events of a device-free sensor carry ``sensor:<sensor_id>`` in the camera
    slot. The location consumer resolves their room here instead of from the camera map,
    which is loaded once at startup; mutations invalidate immediately and a short refresh
    interval handles out-of-process DB edits.
    """

    def __init__(
        self,
        service: PositionSensorService,
        *,
        refresh_s: float = 30.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._service = service
        self._refresh_s = refresh_s
        self._clock = clock
        self._rooms: dict[str, tuple[int, str]] = {}
        self._loaded_at: datetime | None = None
        self._service.register_on_change(self.invalidate)

    def invalidate(self) -> None:
        """Force the next lookup to reload active sensor room mappings."""
        self._loaded_at = None

    def room_for(self, source_id: str) -> tuple[int, str] | None:
        """Return ``(room_id, room_name)`` of the active sensor behind *source_id*, or ``None``."""
        now = self._clock()
        if self._loaded_at is None or (now - self._loaded_at).total_seconds() >= self._refresh_s:
            self._rooms = self._service.rooms_by_source()
            self._loaded_at = now
        return self._rooms.get(source_id)

    def room_id_for(self, source_id: str) -> int | None:
        """Return the room id of the active sensor behind *source_id*, or ``None``."""
        room = self.room_for(source_id)
        return room[0] if room is not None else None
