"""Camera selection cascade for guided-task vision checks."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from backend.core.logging import get_logger
from backend.models.cts_camera import CtsCamera
from backend.models.sensor import Sensor

logger = get_logger(__name__)


@dataclass(frozen=True)
class ResolvedCamera:
    id: str
    source: Literal["cts", "recamera"]


# id/sensor-id -> source. Backed by: a row in cts_cameras => "cts"; a Sensor whose
# origin/type marks it a reCamera => "recamera". Implementation reuses the existing
# registries; see Part C. Returns None for an unknown id (logged, dropped).
CameraSourceResolver = Callable[[str], Literal["cts", "recamera"] | None]


class CameraSourceResolverService:
    """Service to resolve camera ID to source type (cts or recamera)."""

    def __init__(self, db_factory: Callable[[], Any]) -> None:
        self._db_factory = db_factory

    def __call__(self, camera_id: str) -> Literal["cts", "recamera"] | None:
        db = self._db_factory()
        try:
            # 1. Check if it matches a CtsCamera row
            cts_cam = db.query(CtsCamera).filter(CtsCamera.id == camera_id).first()
            if cts_cam is not None:
                return "cts"

            # 2. Check if it matches a Sensor row
            sensor_id = camera_id
            if camera_id.startswith("recamera:"):
                sensor_id = camera_id.split("recamera:", 1)[1]
            sensor = db.query(Sensor).filter(Sensor.id == sensor_id).first()
            if sensor is not None:
                return "recamera"

            logger.warning("camera_source_unknown", camera_id=camera_id)
            return None
        finally:
            db.close()


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


async def select_cameras_tagged(
    *,
    person_id: str,
    step: Any,
    zone_service: ZoneCameraService | None,
    person_location: PersonLocationService | None,
    bucketizer: Any | None,
    event_aggregator: Any | None = None,
    camera_topology: CameraTopology | None,
    identity_resolver: IdentityResolver | None,
    camera_source_resolver: CameraSourceResolver | None = None,
    max_cameras: int = 3,
) -> list[ResolvedCamera]:
    """D5 cascade, returning source-tagged cameras spanning CTS + reCamera.

    Tier order is unchanged (explicit -> detection -> current-zone -> room). Each
    resolved id is tagged via camera_source_resolver. Unknown ids are dropped with
    a warning. Never reads cts_camera.visibility_polygon (D19).
    """
    explicit = _dedupe(getattr(step, "camera_ids", None) or [])
    if explicit:
        tagged = _tag_cameras(explicit, camera_source_resolver)
        return _log_and_cap_tagged("explicit_step", tagged, max_cameras)

    zone_id = getattr(step, "zone_id", None)
    if zone_id is not None and zone_service is not None:
        zone_cameras = _dedupe(zone_service.cameras_for_zone(int(zone_id)))
        if zone_cameras:
            tagged = _tag_cameras(zone_cameras, camera_source_resolver)
            return _log_and_cap_tagged("explicit_zone", tagged, max_cameras)

    identities = await _resolve_identities(identity_resolver, person_id)
    detected = await _detection_driven(
        person_id=person_id,
        identities=identities,
        bucketizer=bucketizer,
        event_aggregator=event_aggregator,
        person_location=person_location,
        camera_source_resolver=camera_source_resolver,
    )
    if detected:
        return _log_and_cap_tagged("detection", detected, max_cameras)

    if zone_service is not None:
        zone = await zone_service.current_zone(person_id)
        current_zone_id = getattr(zone, "id", None)
        if current_zone_id is not None:
            zone_cameras = _dedupe(zone_service.cameras_for_zone(int(current_zone_id)))
            if zone_cameras:
                tagged = _tag_cameras(zone_cameras, camera_source_resolver)
                return _log_and_cap_tagged("current_zone", tagged, max_cameras)

    room_cameras = await _room_fallback(
        person_id=person_id,
        person_location=person_location,
        camera_topology=camera_topology,
    )
    if room_cameras:
        tagged = _tag_cameras(room_cameras, camera_source_resolver)
        return _log_and_cap_tagged("room", tagged, max_cameras)

    logger.info("camera_cascade_tier", person_id=person_id, tier="none", count=0)
    return []


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
    camera_source_resolver: CameraSourceResolver | None = None,
    event_aggregator: Any | None = None,
) -> list[str]:
    """Back-compat id-only wrapper over select_cameras_tagged.

    Existing callers (safety watch) keep working unchanged. New callers (the gate
    runner) use select_cameras_tagged for the source tag.
    """
    tagged = await select_cameras_tagged(
        person_id=person_id,
        step=step,
        zone_service=zone_service,
        person_location=person_location,
        bucketizer=bucketizer,
        event_aggregator=event_aggregator,
        camera_topology=camera_topology,
        identity_resolver=identity_resolver,
        camera_source_resolver=camera_source_resolver,
        max_cameras=max_cameras,
    )
    return [c.id for c in tagged]


def _tag_cameras(
    camera_ids: list[str],
    camera_source_resolver: CameraSourceResolver | None,
    default_source: Literal["cts", "recamera"] = "cts",
) -> list[ResolvedCamera]:
    tagged: list[ResolvedCamera] = []
    for cid in camera_ids:
        if camera_source_resolver is None:
            tagged.append(ResolvedCamera(id=cid, source=default_source))
        else:
            source = camera_source_resolver(cid)
            if source is not None:
                tagged.append(ResolvedCamera(id=cid, source=source))
            else:
                logger.warning("camera_source_unknown", camera_id=cid)
    return tagged


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
    event_aggregator: Any | None,
    person_location: PersonLocationService | None,
    camera_source_resolver: CameraSourceResolver | None,
) -> list[ResolvedCamera]:
    cts_matched: list[str] = []

    target_room_name: str | None = None
    if person_location is not None and (not identities or event_aggregator is not None):
        location = await person_location.where_is(person_id)
        room_name = getattr(location, "room_name", None) if location is not None else None
        target_room_name = str(room_name) if room_name else None

    if bucketizer is not None:
        for camera_id in sorted(bucketizer.buffer_stats()):
            frames = bucketizer.forward_buffer(
                window_id=f"guided_camera_select_{person_id}",
                camera_id=camera_id,
                lookahead_s=0.0,
                eligible_only=False,
            )
            if _camera_matches(frames, identities=identities, room_name=target_room_name):
                cts_matched.append(str(camera_id))

    tagged_cts = _tag_cameras(_dedupe(cts_matched), camera_source_resolver, default_source="cts")

    tagged_recamera: list[ResolvedCamera] = []
    if event_aggregator is not None:
        recamera_ids = await event_aggregator.recent_sensor_ids(
            room_names=[target_room_name] if target_room_name else None,
            limit=10,
            since_minutes=5.0,
        )
        tagged_recamera = _tag_cameras(
            _dedupe(recamera_ids), camera_source_resolver, default_source="recamera"
        )

    return tagged_cts + tagged_recamera


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


def _log_and_cap_tagged(
    tier: str, cameras: list[ResolvedCamera], max_cameras: int
) -> list[ResolvedCamera]:
    capped = cameras[: max(0, max_cameras)]
    logger.info("camera_cascade_tier", tier=tier, count=len(capped), cameras=[c.id for c in capped])
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
