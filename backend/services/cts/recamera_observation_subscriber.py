"""Subscribes to recamera VLM identification events.

Receives push-based recamera observations, writes them to
PersonLocationService as LocationObservation(source='recamera_vlm'),
and publishes to cc.identity_assertions so the tracking-orchestrator can
use the assertion as face-anchor evidence in its Bayesian identity resolver.

This is the CC side of the bidirectional identity flow.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.services.cts.identity_assertion_publisher import IdentityAssertionPublisher
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import FloorPoint

logger = get_logger(__name__)

# Internal queue bounded to prevent memory pressure from bursty recamera events.
_MAX_QUEUE_SIZE = 256


class RecameraObservationSubscriber:
    """Consumes recamera events from an internal queue, writes observations,
    and publishes identity assertions for the orchestrator."""

    def __init__(
        self,
        location_service: PersonLocationService,
        assertion_publisher: IdentityAssertionPublisher,
    ) -> None:
        self._location = location_service
        self._assertion_publisher = assertion_publisher
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
        self._task: asyncio.Task[None] | None = None

    async def enqueue(self, event: dict[str, Any]) -> None:
        """Enqueue a recamera observation for processing.

        Called from the recamera HTTP endpoint (device.py) instead of
        writing directly to the old person-location tables.
        """
        await self._queue.put(event)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("recamera_observation_subscriber_started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        logger.info("recamera_observation_subscriber_stopped")

    async def _consume_loop(self) -> None:
        while True:
            try:
                event = await self._queue.get()
                await self._handle(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("recamera_observation_handle_failed")

    async def _handle(self, event: dict[str, Any]) -> None:
        person_id = event.get("person_id")
        if not person_id:
            return

        observed_at = event.get("observed_at") or datetime.now(UTC)
        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at)

        confidence = float(event.get("confidence", 0.7))
        camera_id = str(event.get("camera_id", ""))
        room_id = event.get("room_id")

        floor_x = event.get("floor_x_m", 0.0)
        floor_y = event.get("floor_y_m", 0.0)
        floor_point = FloorPoint(x_m=float(floor_x), y_m=float(floor_y))

        # 1. Write to PersonLocationService.
        await self._location.ingest_observation(
            person_id=str(person_id),
            observed_at=observed_at,
            source="recamera_vlm",
            source_ref=str(event.get("frame_id", "")),
            floor_point=floor_point,
            room_id=int(room_id) if room_id is not None else None,
            confidence=confidence,
            metadata={
                "camera_id": camera_id,
                "event_type": event.get("event_type", "recamera_vlm"),
            },
        )

        # 2. Publish to cc.identity_assertions for the orchestrator.
        await self._assertion_publisher.publish(
            person_id=str(person_id),
            confidence=confidence,
            camera_id=camera_id,
            captured_at=observed_at,
            floor_x_m=float(floor_x),
            floor_y_m=float(floor_y),
        )
