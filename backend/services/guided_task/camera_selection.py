"""Camera selection cascade for guided-task vision checks."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

from backend.core.logging import get_logger
from backend.models.sensor import Sensor

logger = get_logger(__name__)


class ZoneCameraService(Protocol):
    def cameras_for_zone(self, zone_id: int) -> list[str]: ...
    async def current_zone(self, person_id: str) -> Any | None: ...


class PersonLocationService(Protocol):
    async def where_is(self, person_id: str) -> Any | None: ...


class CameraTopology(Protocol):
    def cameras_in_room(self, room_id: int) -> list[str]: ...


IdentityResolver = Callable[[str], Iterable[str] | Awaitable[Iterable[str]]]


class SensorRoomCameraTopology:
    """Room-to-camera lookup backed by enabled ``Sensor`` rows."""

    def __init__(self, db_factory: Callable[[], Any]) -> None:
        self._db_factory = db_factory

    def cameras_in_room(self, room_id: int) -> list[str]:
        db = self._db_factory()
        try:
            rows = (
                db.query(Sensor)
                .filter(
                    Sensor.room_id == room_id,
                    Sensor.sensor_type == "camera",
                    Sensor.enabled.is_(True),
                )
                .order_by(Sensor.id)
                .all()
            )
            return [str(row.id) for row in rows]
        finally:
            db.close()


async def select_cameras(
    *,
    person_id: str,
    step: Any,
    zone_service: ZoneCameraService | None,
    person_location: PersonLocationService | None,
    bucketizer: Any | None,
    camera_topology: CameraTopology | None,
    identity_resolver: IdentityResolver | None,
    max_cameras: int = 3,
) -> list[str]:
    """Resolve cameras in D5 priority order.

    The first non-empty tier wins. Runtime selection intentionally never reads
    ``cts_camera.visibility_polygon`` because it is a different coordinate
    space and wall-contaminated until Track G lands.
    """
    explicit = _dedupe(getattr(step, "camera_ids", None) or [])
    if explicit:
        return _log_and_cap("explicit_step", explicit, max_cameras)

    zone_id = getattr(step, "zone_id", None)
    if zone_id is not None and zone_service is not None:
        zone_cameras = _dedupe(zone_service.cameras_for_zone(int(zone_id)))
        if zone_cameras:
            return _log_and_cap("explicit_zone", zone_cameras, max_cameras)

    identities = await _resolve_identities(identity_resolver, person_id)
    detected = await _detection_driven(
        person_id=person_id,
        identities=identities,
        bucketizer=bucketizer,
        person_location=person_location,
    )
    if detected:
        return _log_and_cap("detection", detected, max_cameras)

    if zone_service is not None:
        zone = await zone_service.current_zone(person_id)
        current_zone_id = getattr(zone, "id", None)
        if current_zone_id is not None:
            zone_cameras = _dedupe(zone_service.cameras_for_zone(int(current_zone_id)))
            if zone_cameras:
                return _log_and_cap("current_zone", zone_cameras, max_cameras)

    room_cameras = await _room_fallback(
        person_id=person_id,
        person_location=person_location,
        camera_topology=camera_topology,
    )
    if room_cameras:
        return _log_and_cap("room", room_cameras, max_cameras)

    logger.info("camera_cascade_tier", person_id=person_id, tier="none", count=0)
    return []


async def _resolve_identities(
    identity_resolver: IdentityResolver | None,
    person_id: str,
) -> set[str]:
    if identity_resolver is None:
        return set()
    resolved = identity_resolver(person_id)
    if inspect.isawaitable(resolved):
        resolved_items = await resolved
    else:
        resolved_items = resolved
    return {str(identity_id) for identity_id in resolved_items if str(identity_id)}


async def _detection_driven(
    *,
    person_id: str,
    identities: set[str],
    bucketizer: Any | None,
    person_location: PersonLocationService | None,
) -> list[str]:
    if bucketizer is None:
        return []

    target_room_name: str | None = None
    if not identities and person_location is not None:
        location = await person_location.where_is(person_id)
        room_name = getattr(location, "room_name", None) if location is not None else None
        target_room_name = str(room_name) if room_name else None

    matched: list[str] = []
    for camera_id in sorted(bucketizer.buffer_stats()):
        frames = bucketizer.forward_buffer(
            window_id=f"guided_camera_select_{person_id}",
            camera_id=camera_id,
            lookahead_s=0.0,
            eligible_only=False,
        )
        if _camera_matches(frames, identities=identities, room_name=target_room_name):
            matched.append(str(camera_id))
    return _dedupe(matched)


def _camera_matches(
    frames: list[dict[str, Any]],
    *,
    identities: set[str],
    room_name: str | None,
) -> bool:
    for frame in frames:
        detections = frame.get("detections", [])
        if identities:
            for detection in detections:
                if str(detection.get("identity_id", "")) in identities:
                    return True
            continue
        if room_name and frame.get("room_name") != room_name:
            continue
        if detections or int(frame.get("detection_count", 0)) > 0:
            return True
    return False


async def _room_fallback(
    *,
    person_id: str,
    person_location: PersonLocationService | None,
    camera_topology: CameraTopology | None,
) -> list[str]:
    if person_location is None or camera_topology is None:
        return []
    location = await person_location.where_is(person_id)
    room_id = getattr(location, "room_id", None) if location is not None else None
    if room_id is None:
        return []
    return _dedupe(camera_topology.cameras_in_room(int(room_id)))


def _log_and_cap(tier: str, cameras: list[str], max_cameras: int) -> list[str]:
    capped = cameras[: max(0, max_cameras)]
    logger.info("camera_cascade_tier", tier=tier, count=len(capped), cameras=capped)
    return capped


def _dedupe(items: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
