"""N4: WorldSnapshotPublisher — debounced 5 Hz cts_world_snapshot broadcaster."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.services.cts._types import ConnectionManager

logger = get_logger(__name__)

_DEBOUNCE_S = 0.200  # 5 Hz max
_HEARTBEAT_S = 5.0  # heartbeat when idle


class WorldSnapshotPublisher:
    """Publish cts_world_snapshot at most at 5 Hz (200 ms debounce).

    Call mark_dirty() on each PH update; the loop flushes after the burst settles.
    A heartbeat fires every 5 s so the frontend does not flip to stale when the
    scene is static.
    """

    def __init__(
        self,
        ws_manager: ConnectionManager,
        person_location_service: object | None = None,
        debounce_s: float = _DEBOUNCE_S,
        heartbeat_s: float = _HEARTBEAT_S,
    ) -> None:
        self._ws_manager = ws_manager
        self._pls = person_location_service
        self._debounce_s = debounce_s
        self._heartbeat_s = heartbeat_s
        self._pending_phs: list[dict[str, Any]] = []
        self._dirty = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_snapshot_id: str = ""

    def mark_dirty(self, ph_data_list: list[dict[str, Any]]) -> None:
        """Merge new PH data and signal that a snapshot is due."""
        self._pending_phs = ph_data_list
        self._dirty.set()

    async def start(self) -> None:
        """Start the background publish loop."""
        self._task = asyncio.create_task(self._loop(), name="world_snapshot_publisher")

    async def stop(self) -> None:
        """Cancel the background loop and wait for it to exit."""
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._dirty.wait(), timeout=self._heartbeat_s)
                await asyncio.sleep(self._debounce_s)
                self._dirty.clear()
            except TimeoutError:
                pass
            await self._publish()

    async def _publish(self) -> None:
        inferred_rooms = await self._fetch_inferred_rooms()
        phs = list(self._pending_phs)

        try:
            content = json.dumps(
                {"phs": phs, "rooms": inferred_rooms}, sort_keys=True, default=str
            )
            snapshot_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        except Exception:
            logger.warning("world_snapshot_hash_failed")
            snapshot_id = datetime.now(UTC).isoformat()

        if snapshot_id == self._last_snapshot_id:
            return

        self._last_snapshot_id = snapshot_id
        payload: dict[str, Any] = {
            "type": "cts_world_snapshot",
            "snapshot_id": snapshot_id,
            "captured_at": datetime.now(UTC).isoformat(),
            "phs": phs,
            "inferred_rooms": inferred_rooms,
        }
        try:
            await self._ws_manager.broadcast(payload)
        except Exception:
            logger.exception("world_snapshot_broadcast_error")

    async def _fetch_inferred_rooms(self) -> list[dict[str, Any]]:
        if self._pls is None:
            return []
        try:
            location_map = await self._pls.where_is_everyone()
            result: list[dict[str, Any]] = []
            for person_id, location in location_map.items():
                if getattr(location, "is_inferred", False):
                    result.append(
                        {
                            "room_id": location.room_id,
                            "room_name": location.room_name,
                            "person_id": str(person_id),
                            "since": location.since.isoformat() if location.since else None,
                        }
                    )
            return result
        except Exception:
            logger.warning("inferred_rooms_fetch_failed")
            return []
