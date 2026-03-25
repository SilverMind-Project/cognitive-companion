"""
EventAggregator v2 – batches per-sensor motion/capture events, manages
cooldowns, and orchestrates media lifecycle (upload -> cache -> expire -> delete).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.media_cache import MediaCache

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

        buf = self.buffers.pop(sensor_id, [])
        if not buf:
            logger.debug("flush_empty_buffer", sensor_id=sensor_id)
            return

        logger.info("flush_triggered", sensor_id=sensor_id, count=len(buf))

        # Persist each media path to the MediaCache table
        now_utc = datetime.now(timezone.utc)
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
        except Exception:
            db.rollback()
            logger.exception("flush_db_error", sensor_id=sensor_id)
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

    async def get_recent_images(
        self, sensor_id: str, limit: int = 10
    ) -> list[str]:
        """Return presigned URLs for the most recent non-deleted, non-expired
        images belonging to *sensor_id*, regenerating URLs as needed.
        """
        now_utc = datetime.now(timezone.utc)

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
        now_utc = datetime.now(timezone.utc)

        db: Session = self._db_session_factory()
        try:
            stmt = select(MediaCache).where(
                MediaCache.deleted.is_(False),
                MediaCache.expires_at <= now_utc,
            )
            expired_rows: list[MediaCache] = list(
                db.execute(stmt).scalars().all()
            )

            if not expired_rows:
                return

            logger.info("cleanup_expired_media_start", count=len(expired_rows))
            for row in expired_rows:
                try:
                    self._minio.delete_object(row.object_name)
                except Exception:
                    logger.exception(
                        "cleanup_delete_error", object_name=row.object_name
                    )
                row.deleted = True

            db.commit()
            logger.info("cleanup_expired_media_done", deleted=len(expired_rows))
        except Exception:
            db.rollback()
            logger.exception("cleanup_expired_media_error")
            raise
        finally:
            db.close()

    # -- internal helpers -----------------------------------------------------

    def _start_timer(self, sensor_id: str) -> None:
        """Start a window timer that flushes after ``window_seconds``."""
        self._cancel_timer(sensor_id)

        async def _timer_body() -> None:
            await asyncio.sleep(self.window_seconds)
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
