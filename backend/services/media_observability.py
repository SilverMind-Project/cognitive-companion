"""Unified read service for live aggregator and retained media state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.cts_camera import CtsCamera
from backend.models.media_cache import MediaCache
from backend.models.room import Room
from backend.models.sensor import Sensor
from backend.schemas.media_observability import (
    AggregatorStateListEnvelope,
    CameraAggregatorStateOut,
    MediaBufferCameraOut,
    MediaBufferImageOut,
    MediaBufferListEnvelope,
)
from backend.services.aggregation import AggregatorStatsProvider, CameraBufferState

logger = get_logger(__name__)

DBSessionFactory = Callable[[], Session]
BucketizerProvider = Callable[[], AggregatorStatsProvider | None]


class MediaObservabilityService:
    """Merge runtime aggregator state and expose retained reCamera media."""

    def __init__(
        self,
        db_factory: DBSessionFactory,
        event_aggregator: AggregatorStatsProvider | None,
        get_bucketizer: BucketizerProvider,
        minio_client: MinioClient | None,
    ) -> None:
        self._db_factory = db_factory
        self._event_aggregator = event_aggregator
        self._get_bucketizer = get_bucketizer
        self._minio = minio_client

    def aggregator_state(
        self,
        origin: str | None = None,
        camera_id: str | None = None,
        room_name: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AggregatorStateListEnvelope:
        """Return enriched, filtered runtime state for both aggregators."""
        states = self._collect_states()
        recamera_names, cts_names = self._camera_name_maps()

        items = [
            self._enrich_state(
                state,
                recamera_names=recamera_names,
                cts_names=cts_names,
            )
            for state in states
        ]
        filtered = [
            item
            for item in items
            if self._matches_filters(
                item,
                origin=origin,
                camera_id=camera_id,
                room_name=room_name,
                query=query,
            )
        ]
        filtered.sort(
            key=lambda item: (
                item.origin,
                (item.display_name or "").casefold(),
                item.camera_id.casefold(),
            )
        )
        return AggregatorStateListEnvelope(
            items=filtered[offset : offset + limit],
            total=len(filtered),
        )

    def media_buffer(
        self,
        sensor_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> MediaBufferListEnvelope:
        """Return paginated camera rows with retained and pending media."""
        db = self._db_factory()
        try:
            camera_query = db.query(Sensor).filter(
                Sensor.sensor_type == "camera",
                Sensor.enabled.is_(True),
            )
            if sensor_id:
                camera_query = camera_query.filter(Sensor.id == sensor_id)

            total = camera_query.count()
            cameras = (
                camera_query.order_by(Sensor.name, Sensor.id).offset(offset).limit(limit).all()
            )
            state_by_camera = self._recamera_state_by_camera()
            now_utc = datetime.now(UTC)
            items: list[MediaBufferCameraOut] = []
            url_refresh_needed = False

            for camera in cameras:
                state = state_by_camera.get(camera.id)
                images, refreshed = self._media_images(
                    db,
                    sensor_id=camera.id,
                    now_utc=now_utc,
                    limit=limit,
                )
                url_refresh_needed = url_refresh_needed or refreshed
                items.append(
                    MediaBufferCameraOut(
                        sensor_id=camera.id,
                        sensor_name=camera.name,
                        room_name=camera.room.name if camera.room else None,
                        buffer_pending=state.pending_flush if state and state.pending_flush else 0,
                        cooldown_remaining_seconds=(
                            state.cooldown_remaining_seconds if state else None
                        ),
                        images=images,
                    )
                )

            if url_refresh_needed:
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("media_buffer_presign_commit_error")

            return MediaBufferListEnvelope(items=items, total=total)
        finally:
            db.close()

    def _collect_states(self) -> list[CameraBufferState]:
        states: list[CameraBufferState] = []
        missing: list[str] = []

        if self._event_aggregator is None:
            missing.append("event_aggregator")
        else:
            states.extend(self._event_aggregator.buffer_state())

        bucketizer = self._get_bucketizer()
        if bucketizer is None:
            missing.append("cts_bucketizer")
        else:
            states.extend(bucketizer.buffer_state())

        if missing:
            logger.warning(
                "media_observability_aggregators_unavailable",
                aggregators=missing,
            )
        return states

    def _camera_name_maps(
        self,
    ) -> tuple[dict[str, tuple[str, str | None]], dict[str, tuple[str, str | None]]]:
        db = self._db_factory()
        try:
            recamera_rows = (
                db.query(Sensor.id, Sensor.name, Room.name)
                .outerjoin(Room, Sensor.room_id == Room.id)
                .filter(Sensor.sensor_type == "camera")
                .all()
            )
            cts_rows = db.query(CtsCamera.id, CtsCamera.name, CtsCamera.room_name).all()
            return (
                {
                    sensor_id: (display_name, resolved_room)
                    for sensor_id, display_name, resolved_room in recamera_rows
                },
                {
                    camera_id: (display_name, resolved_room or None)
                    for camera_id, display_name, resolved_room in cts_rows
                },
            )
        finally:
            db.close()

    @staticmethod
    def _enrich_state(
        state: CameraBufferState,
        *,
        recamera_names: dict[str, tuple[str, str | None]],
        cts_names: dict[str, tuple[str, str | None]],
    ) -> CameraAggregatorStateOut:
        name_map = recamera_names if state.origin == "recamera" else cts_names
        display_name, room_name = name_map.get(state.camera_id, (None, None))
        return CameraAggregatorStateOut(
            **state.model_dump(),
            display_name=display_name,
            room_name=room_name,
        )

    @staticmethod
    def _matches_filters(
        item: CameraAggregatorStateOut,
        *,
        origin: str | None,
        camera_id: str | None,
        room_name: str | None,
        query: str | None,
    ) -> bool:
        if origin is not None and item.origin != origin:
            return False
        if camera_id is not None and item.camera_id != camera_id:
            return False
        if room_name is not None and (item.room_name or "").casefold() != room_name.casefold():
            return False
        if query:
            needle = query.casefold()
            haystacks = (item.display_name or "", item.camera_id, item.room_name or "")
            if not any(needle in value.casefold() for value in haystacks):
                return False
        return True

    def _recamera_state_by_camera(self) -> dict[str, CameraBufferState]:
        if self._event_aggregator is None:
            logger.warning(
                "media_observability_aggregators_unavailable",
                aggregators=["event_aggregator"],
            )
            return {}
        return {
            state.camera_id: state
            for state in self._event_aggregator.buffer_state()
            if state.origin == "recamera"
        }

    def _media_images(
        self,
        db: Session,
        *,
        sensor_id: str,
        now_utc: datetime,
        limit: int,
    ) -> tuple[list[MediaBufferImageOut], bool]:
        stmt = (
            select(MediaCache)
            .where(
                MediaCache.sensor_id == sensor_id,
                MediaCache.deleted.is_(False),
                MediaCache.expires_at > now_utc,
            )
            .order_by(MediaCache.captured_at.desc())
            .limit(limit)
        )
        rows: list[MediaCache] = list(db.execute(stmt).scalars().all())
        images: list[MediaBufferImageOut] = []
        refreshed = False

        for row in rows:
            url = row.presigned_url or ""
            if self._minio is not None:
                try:
                    url = self._minio.generate_presigned_url(row.object_name)
                    row.presigned_url = url
                    refreshed = True
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "media_buffer_presign_failed",
                        object_name=row.object_name,
                        sensor_id=sensor_id,
                    )
                    continue
            images.append(
                MediaBufferImageOut(
                    id=row.id,
                    url=url,
                    object_name=row.object_name,
                    captured_at=row.captured_at.isoformat(),
                    expires_at=row.expires_at.isoformat(),
                )
            )
        return images, refreshed
