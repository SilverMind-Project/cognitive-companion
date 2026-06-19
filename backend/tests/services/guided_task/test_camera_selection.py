from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from backend.services.guided_task.camera_selection import (
    ResolvedCamera,
    select_cameras,
    select_cameras_tagged,
)


@dataclass
class _Step:
    camera_ids: list[str] | None = None
    zone_id: int | None = None


@dataclass
class _Zone:
    id: int


@dataclass
class _Location:
    room_id: int
    room_name: str


class _ZoneService:
    def __init__(self) -> None:
        self.current = _Zone(9)

    def cameras_for_zone(self, zone_id: int) -> list[str]:
        return {7: ["zone-cam"], 9: ["current-zone-cam"]}.get(zone_id, [])

    async def current_zone(self, person_id: str) -> _Zone:
        return self.current


class _LocationService:
    async def where_is(self, person_id: str) -> _Location:
        return _Location(room_id=3, room_name="kitchen")


class _Bucketizer:
    def __init__(self, buffers: dict[str, list[dict]]) -> None:
        self._buffers = buffers

    def buffer_stats(self) -> dict[str, int]:
        return {camera_id: len(frames) for camera_id, frames in self._buffers.items()}

    def forward_buffer(self, window_id, camera_id, lookahead_s, eligible_only=False):
        return list(self._buffers.get(camera_id, []))


class _Topology:
    visibility_polygon = "must not be used"

    def cameras_in_room(self, room_id: int) -> list[str]:
        return ["room-cam"] if room_id == 3 else []


async def test_explicit_step_camera_ids_win() -> None:
    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(camera_ids=["cam-a", "cam-b"]),
        zone_service=_ZoneService(),
        person_location=_LocationService(),
        bucketizer=None,
        camera_topology=_Topology(),
        identity_resolver=lambda _person_id: {"resident-1"},
    )

    assert cameras == ["cam-a", "cam-b"]


async def test_zone_camera_ids_used_when_no_step_cameras() -> None:
    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(zone_id=7),
        zone_service=_ZoneService(),
        person_location=_LocationService(),
        bucketizer=None,
        camera_topology=_Topology(),
        identity_resolver=lambda _person_id: {"resident-1"},
    )

    assert cameras == ["zone-cam"]


async def test_detection_driven_when_no_explicit() -> None:
    bucketizer = _Bucketizer(
        {
            "cam-1": [{"detections": [{"identity_id": "resident-1"}]}],
            "cam-2": [{"detections": [{"identity_id": "other"}]}],
        }
    )

    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(),
        zone_service=None,
        person_location=_LocationService(),
        bucketizer=bucketizer,
        camera_topology=_Topology(),
        identity_resolver=lambda _person_id: {"resident-1"},
    )

    assert cameras == ["cam-1"]


async def test_detection_fallback_to_room_detections_when_identity_unresolved() -> None:
    bucketizer = _Bucketizer(
        {
            "cam-1": [{"room_name": "kitchen", "detection_count": 1, "detections": [{}]}],
            "cam-2": [{"room_name": "hall", "detection_count": 1, "detections": [{}]}],
        }
    )

    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(),
        zone_service=None,
        person_location=_LocationService(),
        bucketizer=bucketizer,
        camera_topology=_Topology(),
        identity_resolver=lambda _person_id: set(),
    )

    assert cameras == ["cam-1"]


async def test_zone_driven_when_no_detections() -> None:
    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(),
        zone_service=_ZoneService(),
        person_location=_LocationService(),
        bucketizer=_Bucketizer({}),
        camera_topology=_Topology(),
        identity_resolver=lambda _person_id: {"resident-1"},
    )

    assert cameras == ["current-zone-cam"]


async def test_room_fallback_when_no_zone() -> None:
    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(),
        zone_service=None,
        person_location=_LocationService(),
        bucketizer=None,
        camera_topology=_Topology(),
        identity_resolver=lambda _person_id: set(),
    )

    assert cameras == ["room-cam"]


async def test_caps_at_max_cameras() -> None:
    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(camera_ids=["cam-a", "cam-b", "cam-c"]),
        zone_service=None,
        person_location=None,
        bucketizer=None,
        camera_topology=None,
        identity_resolver=None,
        max_cameras=2,
    )

    assert cameras == ["cam-a", "cam-b"]


async def test_never_reads_visibility_polygon() -> None:
    class _ExplodingTopology(_Topology):
        @property
        def visibility_polygon(self):
            raise AssertionError("visibility polygon must not be read")

    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(),
        zone_service=None,
        person_location=_LocationService(),
        bucketizer=None,
        camera_topology=_ExplodingTopology(),
        identity_resolver=None,
    )

    assert cameras == ["room-cam"]


async def test_tagged_explicit_cameras_carry_source() -> None:
    def resolver(cid: str):
        return "recamera" if cid == "cam-c" else "cts"

    cameras = await select_cameras_tagged(
        person_id="resident-1",
        step=_Step(camera_ids=["cam-a", "cam-b", "cam-c"]),
        zone_service=None,
        person_location=None,
        bucketizer=None,
        camera_topology=None,
        identity_resolver=None,
        camera_source_resolver=resolver,
    )

    assert cameras == [
        ResolvedCamera(id="cam-a", source="cts"),
        ResolvedCamera(id="cam-b", source="cts"),
        ResolvedCamera(id="cam-c", source="recamera"),
    ]


async def test_tagged_detection_tier_includes_recamera_when_aggregator_present() -> None:
    aggregator = AsyncMock()
    aggregator.query_recent_media.return_value = ["https://minio/recamera_image.jpg"]
    aggregator._minio = MagicMock()
    aggregator._minio.extract_object_name.side_effect = lambda url: url.split("/")[-1]

    mock_row = MagicMock()
    mock_row.object_name = "recamera_image.jpg"
    mock_row.sensor_id = "sensor-recamera"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_row]
    aggregator._db_session_factory = lambda: mock_db

    cameras = await select_cameras_tagged(
        person_id="resident-1",
        step=_Step(),
        zone_service=None,
        person_location=_LocationService(),
        bucketizer=None,
        event_aggregator=aggregator,
        camera_topology=None,
        identity_resolver=lambda _person_id: set(),
        camera_source_resolver=lambda cid: "recamera" if cid == "sensor-recamera" else None,
    )

    assert cameras == [ResolvedCamera(id="sensor-recamera", source="recamera")]


async def test_tagged_degrades_to_cts_only_when_no_aggregator() -> None:
    bucketizer = _Bucketizer(
        {
            "cam-1": [{"detections": [{"identity_id": "resident-1"}]}],
        }
    )

    cameras = await select_cameras_tagged(
        person_id="resident-1",
        step=_Step(),
        zone_service=None,
        person_location=_LocationService(),
        bucketizer=bucketizer,
        event_aggregator=None,
        camera_topology=None,
        identity_resolver=lambda _person_id: {"resident-1"},
        camera_source_resolver=None,
    )

    assert cameras == [ResolvedCamera(id="cam-1", source="cts")]


async def test_unknown_id_dropped_and_warned() -> None:
    cameras = await select_cameras_tagged(
        person_id="resident-1",
        step=_Step(camera_ids=["cam-unknown"]),
        zone_service=None,
        person_location=None,
        bucketizer=None,
        camera_topology=None,
        identity_resolver=None,
        camera_source_resolver=lambda cid: None,
    )

    assert cameras == []


async def test_select_cameras_wrapper_returns_ids_only() -> None:
    def resolver(cid: str):
        return "recamera" if cid == "cam-c" else "cts"

    cameras = await select_cameras(
        person_id="resident-1",
        step=_Step(camera_ids=["cam-a", "cam-b", "cam-c"]),
        zone_service=None,
        person_location=None,
        bucketizer=None,
        camera_topology=None,
        identity_resolver=None,
        camera_source_resolver=resolver,
    )

    assert cameras == ["cam-a", "cam-b", "cam-c"]


async def test_tagged_never_reads_visibility_polygon() -> None:
    class _ExplodingTopology(_Topology):
        @property
        def visibility_polygon(self):
            raise AssertionError("visibility polygon must not be read")

    cameras = await select_cameras_tagged(
        person_id="resident-1",
        step=_Step(),
        zone_service=None,
        person_location=_LocationService(),
        bucketizer=None,
        camera_topology=_ExplodingTopology(),
        identity_resolver=None,
        camera_source_resolver=lambda cid: "cts" if cid == "room-cam" else None,
    )

    assert cameras == [ResolvedCamera(id="room-cam", source="cts")]
