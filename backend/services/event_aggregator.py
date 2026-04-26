"""
EventAggregator v2 - batches per-sensor motion/capture events, manages
cooldowns, and orchestrates media lifecycle (upload -> cache -> expire -> delete).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.media_cache import MediaCache
from backend.models.room import Room
from backend.models.sensor import Sensor

logger = get_logger(__name__)

# Type alias for the processing callback invoked on flush.
ProcessCallback = Callable[[str, list[str]], Awaitable[Any]]


class EventAggregator:
    """Collects per-sensor media events, batches them, and triggers processing."""

    def __init__(
        self,
        config: dict[str, Any],
        db_session_factory: Callable[[], Session],
        minio_client: MinioClient,
        process_callback: ProcessCallback,
    ) -> None:
        self.batch_size: int = config.get("batch_size", 5)
        self.window_seconds: float = config.get("window_seconds", 30.0)
        self.cooldown_seconds: float = config.get("cooldown_seconds", 60.0)
        self.media_retention_minutes: int = config.get("media_retention_minutes", 30)

        self._db_session_factory = db_session_factory
        self._minio = minio_client
        self._process_callback = process_callback

        # Per-sensor state
        self.buffers: dict[str, list[str]] = {}
        self.timers: dict[str, asyncio.Task[None]] = {}
        self.cooldowns: dict[str, float] = {}

        logger.info(
            "event_aggregator_initialized",
            batch_size=self.batch_size,
            window_seconds=self.window_seconds,
            cooldown_seconds=self.cooldown_seconds,
            media_retention_minutes=self.media_retention_minutes,
        )

    # -- public API -----------------------------------------------------------

    async def add_event(self, sensor_id: str, media_path: str) -> None:
        """Add a media event for *sensor_id*.

        Respects cooldown, starts a window timer on the first event of a batch,
        and auto-flushes when the batch reaches ``batch_size``.
        """
        now = time.monotonic()

        # Respect cooldown
        cooldown_until = self.cooldowns.get(sensor_id, 0.0)
        if now < cooldown_until:
            remaining = cooldown_until - now
            logger.debug(
                "event_skipped_cooldown",
                sensor_id=sensor_id,
                remaining_seconds=round(remaining, 1),
            )
            return

        buf = self.buffers.setdefault(sensor_id, [])
        buf.append(media_path)
        logger.debug(
            "event_added",
            sensor_id=sensor_id,
            buffer_size=len(buf),
            media_path=media_path,
        )

        # Start a window timer on first event
        if len(buf) == 1:
            self._start_timer(sensor_id)

        # Auto-flush when the batch is full
        if len(buf) >= self.batch_size:
            await self.flush(sensor_id)

    async def flush(self, sensor_id: str) -> None:
        """Flush the buffer for *sensor_id*: persist to MediaCache,
        invoke the processing callback, and set a cooldown.
        """
        self._cancel_timer(sensor_id)

        # Peek at the buffer before removing it so we can restore on failure.
        buf = self.buffers.get(sensor_id, [])
        if not buf:
            self.buffers.pop(sensor_id, None)
            logger.debug("flush_empty_buffer", sensor_id=sensor_id)
            return

        logger.info("flush_triggered", sensor_id=sensor_id, count=len(buf))

        # Persist each media path to the MediaCache table.  Only remove the
        # buffer from memory once the DB write succeeds  that way a transient
        # DB error doesn't silently discard media paths.
        now_utc = datetime.now(UTC)
        expires_at = now_utc + timedelta(minutes=self.media_retention_minutes)

        db: Session = self._db_session_factory()
        try:
            for media_path in buf:
                object_name = self._minio.extract_object_name(media_path)
                presigned_url = self._minio.generate_presigned_url(object_name)
                entry = MediaCache(
                    object_name=object_name,
                    presigned_url=presigned_url,
                    sensor_id=sensor_id,
                    captured_at=now_utc,
                    expires_at=expires_at,
                    deleted=False,
                )
                db.merge(entry)
            db.commit()
            # DB write succeeded  now remove the buffer.
            self.buffers.pop(sensor_id, None)
        except Exception:
            db.rollback()
            logger.exception("flush_db_error", sensor_id=sensor_id, paths=buf)
            raise
        finally:
            db.close()

        # Trigger async processing callback
        try:
            await self._process_callback(sensor_id, buf)
        except Exception:
            logger.exception("process_callback_error", sensor_id=sensor_id)

        # Set cooldown
        self.cooldowns[sensor_id] = time.monotonic() + self.cooldown_seconds
        logger.debug(
            "cooldown_set",
            sensor_id=sensor_id,
            cooldown_seconds=self.cooldown_seconds,
        )

    async def get_recent_images(self, sensor_id: str, limit: int = 10) -> list[str]:
        """Return presigned URLs for the most recent non-deleted, non-expired
        images belonging to *sensor_id*, regenerating URLs as needed.
        """
        now_utc = datetime.now(UTC)

        db: Session = self._db_session_factory()
        try:
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

            urls: list[str] = []
            for row in rows:
                url = self._minio.generate_presigned_url(row.object_name)
                # Update cached presigned URL
                row.presigned_url = url
                urls.append(url)

            db.commit()
        except Exception:
            db.rollback()
            logger.exception("get_recent_images_error", sensor_id=sensor_id)
            raise
        finally:
            db.close()

        return urls

    async def cleanup_expired_media(self) -> None:
        """Delete expired objects from MinIO and mark them as deleted in the
        MediaCache table.
        """
        now_utc = datetime.now(UTC)

        db: Session = self._db_session_factory()
        try:
            stmt = select(MediaCache).where(
                MediaCache.deleted.is_(False),
                MediaCache.expires_at <= now_utc,
            )
            expired_rows: list[MediaCache] = list(db.execute(stmt).scalars().all())

            if not expired_rows:
                return

            logger.info("cleanup_expired_media_start", count=len(expired_rows))
            for row in expired_rows:
                try:
                    self._minio.delete_object(row.object_name)
                except Exception:
                    logger.exception("cleanup_delete_error", object_name=row.object_name)
                row.deleted = True

            db.commit()
            logger.info("cleanup_expired_media_done", deleted=len(expired_rows))
        except Exception:
            db.rollback()
            logger.exception("cleanup_expired_media_error")
            raise
        finally:
            db.close()

    async def query_recent_media(
        self,
        sensor_ids: list[str] | None = None,
        room_names: list[str] | None = None,
        limit: int = 5,
        since_minutes: float | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
    ) -> list[str]:
        """Query recent images from MediaCache with filters.

        Does **not** affect flush buffers or cooldown. Returns presigned URLs.

        Parameters
        ----------
        sensor_ids:
            Restrict to these sensor IDs. ``None`` means no sensor filter
            (but *room_names* may still apply).
        room_names:
            Restrict to cameras in these rooms. Resolved via the
            ``Sensor.room`` relationship. ``None`` means no room filter.
        limit:
            Maximum number of images to return.
        since_minutes:
            Only include images captured within the last *since_minutes*.
        time_start / time_end:
            ``"HH:MM"`` strings defining a time-of-day window (fixed to
            today). Alternative to *since_minutes*.
        """
        now_utc = datetime.now(UTC)

        db: Session = self._db_session_factory()
        try:
            stmt = select(MediaCache).where(
                MediaCache.deleted.is_(False),
                MediaCache.expires_at > now_utc,
            )

            # Sensor filter
            resolved_sensor_ids: list[str] | None = None

            if sensor_ids:
                resolved_sensor_ids = list(sensor_ids)

            # Room-name filter: resolve room names to camera sensor IDs
            if room_names:
                room_sensor_rows = (
                    db.query(Sensor.id)
                    .join(Room, Sensor.room_id == Room.id)
                    .filter(
                        Room.name.in_(room_names),
                        Sensor.sensor_type == "camera",
                        Sensor.enabled.is_(True),
                    )
                    .all()
                )
                room_sensor_ids = [row[0] for row in room_sensor_rows]
                if resolved_sensor_ids is not None:
                    # Intersect with explicit sensor_ids
                    resolved_sensor_ids = [s for s in resolved_sensor_ids if s in room_sensor_ids]
                else:
                    resolved_sensor_ids = room_sensor_ids

            if resolved_sensor_ids is not None:
                stmt = stmt.where(MediaCache.sensor_id.in_(resolved_sensor_ids))

            # Time filter: since_minutes
            if since_minutes is not None:
                cutoff = now_utc - timedelta(minutes=since_minutes)
                stmt = stmt.where(MediaCache.captured_at >= cutoff)

            # Time filter: time_start / time_end (today only)
            if time_start or time_end:
                if time_start:
                    match = re.match(r"(\d{1,2}):(\d{2})", time_start)
                    if match:
                        h, m = int(match.group(1)), int(match.group(2))
                        start_dt = now_utc.replace(hour=h, minute=m, second=0, microsecond=0)
                        stmt = stmt.where(MediaCache.captured_at >= start_dt)
                if time_end:
                    match = re.match(r"(\d{1,2}):(\d{2})", time_end)
                    if match:
                        h, m = int(match.group(1)), int(match.group(2))
                        end_dt = now_utc.replace(hour=h, minute=m, second=59, microsecond=999999)
                        stmt = stmt.where(MediaCache.captured_at <= end_dt)

            stmt = stmt.order_by(MediaCache.captured_at.desc()).limit(limit)
            rows: list[MediaCache] = list(db.execute(stmt).scalars().all())

            urls: list[str] = []
            for row in rows:
                url = self._minio.generate_presigned_url(row.object_name)
                row.presigned_url = url
                urls.append(url)

            db.commit()
        except Exception:
            db.rollback()
            logger.exception("query_recent_media_error")
            raise
        finally:
            db.close()

        return urls

    async def query_media_by_sensor(
        self,
        sensor_ids_ordered: list[str],
        images_per_sensor: int = 3,
        sensor_frame_limits: dict[str, int] | None = None,
        max_images: int = 15,
        since_minutes: float | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        chronological: bool = True,
    ) -> list[str]:
        """Return images grouped by sensor with configurable per-sensor limits.

        Images are assembled as: all images for sensor_ids_ordered[0], then
        sensor_ids_ordered[1], etc.  Within each sensor group, images are
        sorted chronologically (oldest first) when *chronological* is ``True``
        (for inter-frame analysis) or newest-first otherwise.

        Parameters
        ----------
        sensor_ids_ordered:
            Sensor IDs in the desired group order.
        images_per_sensor:
            Default maximum images to include from each sensor.
        sensor_frame_limits:
            Per-sensor override dict mapping sensor ID -> max images.
        max_images:
            Hard cap on total images returned across all sensors.
        since_minutes / time_start / time_end:
            Same time filter semantics as :meth:`query_recent_media`.
        chronological:
            When ``True``, intra-sensor ordering is oldest-first.
            When ``False``, newest-first.
        """
        now_utc = datetime.now(UTC)

        db: Session = self._db_session_factory()
        try:
            base_stmt = select(MediaCache).where(
                MediaCache.deleted.is_(False),
                MediaCache.expires_at > now_utc,
                MediaCache.sensor_id.in_(sensor_ids_ordered),
            )

            if since_minutes is not None:
                cutoff = now_utc - timedelta(minutes=since_minutes)
                base_stmt = base_stmt.where(MediaCache.captured_at >= cutoff)

            if time_start or time_end:
                if time_start:
                    match = re.match(r"(\d{1,2}):(\d{2})", time_start)
                    if match:
                        h, m = int(match.group(1)), int(match.group(2))
                        start_dt = now_utc.replace(hour=h, minute=m, second=0, microsecond=0)
                        base_stmt = base_stmt.where(MediaCache.captured_at >= start_dt)
                if time_end:
                    match = re.match(r"(\d{1,2}):(\d{2})", time_end)
                    if match:
                        h, m = int(match.group(1)), int(match.group(2))
                        end_dt = now_utc.replace(hour=h, minute=m, second=59, microsecond=999999)
                        base_stmt = base_stmt.where(MediaCache.captured_at <= end_dt)

            # Fetch all matching rows; group and sort in Python for predictable ordering.
            rows: list[MediaCache] = list(db.execute(base_stmt).scalars().all())

            # Group by sensor, apply per-sensor limits and ordering.
            by_sensor: dict[str, list[MediaCache]] = {sid: [] for sid in sensor_ids_ordered}
            for row in rows:
                if row.sensor_id in by_sensor:
                    by_sensor[row.sensor_id].append(row)
            limits = sensor_frame_limits or {}
            for sid in sensor_ids_ordered:
                limit = limits.get(sid, images_per_sensor)
                by_sensor[sid].sort(key=lambda r: r.captured_at)
                if not chronological:
                    by_sensor[sid] = list(reversed(by_sensor[sid]))
                by_sensor[sid] = by_sensor[sid][:limit]

            # Flatten in sensor order, apply overall cap.
            ordered_rows: list[MediaCache] = []
            for sid in sensor_ids_ordered:
                ordered_rows.extend(by_sensor[sid])
            ordered_rows = ordered_rows[:max_images]

            urls: list[str] = []
            for row in ordered_rows:
                url = self._minio.generate_presigned_url(row.object_name)
                row.presigned_url = url
                urls.append(url)

            db.commit()
        except Exception:
            db.rollback()
            logger.exception("query_media_by_sensor_error")
            raise
        finally:
            db.close()

        return urls

    # -- internal helpers -----------------------------------------------------

    def _start_timer(self, sensor_id: str) -> None:
        """Start a window timer that flushes after ``window_seconds``."""
        self._cancel_timer(sensor_id)

        async def _timer_body() -> None:
            await asyncio.sleep(self.window_seconds)
            # Remove self from timers before calling flush so that flush's
            # _cancel_timer call does not cancel the currently-running task.
            self.timers.pop(sensor_id, None)
            await self.flush(sensor_id)

        task = asyncio.create_task(_timer_body(), name=f"flush-timer-{sensor_id}")
        self.timers[sensor_id] = task
        logger.debug(
            "timer_started",
            sensor_id=sensor_id,
            window_seconds=self.window_seconds,
        )

    def _cancel_timer(self, sensor_id: str) -> None:
        """Cancel an active flush timer for *sensor_id* if one exists."""
        task = self.timers.pop(sensor_id, None)
        if task is not None and not task.done():
            task.cancel()
            logger.debug("timer_cancelled", sensor_id=sensor_id)
