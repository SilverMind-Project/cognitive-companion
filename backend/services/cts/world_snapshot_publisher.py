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
_HEARTBEAT_S = 5.0   # heartbeat when idle

# Two camera observations for the same identified person are considered
# simultaneous (and eligible for position averaging) when their
# last_observed_at values are within this many seconds of each other.
_MULTI_CAM_WINDOW_S = 2.0


def _ts(iso: str | None) -> datetime | None:
    """Parse an ISO timestamp string; return None on failure."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _average_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple camera observations for the same identified person.

    Uses the most recently observed entry as the base (identity metadata,
    posture, room, etc.) and replaces floor_xy_m with the mean of all
    calibrated positions.  Falls back to the base position when no
    observation is calibrated.
    """
    base = max(observations, key=lambda o: o.get("last_observed_at") or "")
    calibrated = [o for o in observations if not o.get("uncalibrated")]
    if len(calibrated) >= 2:
        avg_x = sum(o["floor_xy_m"][0] for o in calibrated) / len(calibrated)
        avg_y = sum(o["floor_xy_m"][1] for o in calibrated) / len(calibrated)
        return {**base, "floor_xy_m": [avg_x, avg_y], "uncalibrated": False}
    if calibrated:
        return {**base, "floor_xy_m": calibrated[0]["floor_xy_m"], "uncalibrated": False}
    return base


class WorldSnapshotPublisher:
    """Publish cts_world_snapshot at most at 5 Hz (200 ms debounce).

    Internal state is a per-camera registry:
        _camera_phs: {camera_id: {ph_id: ph_data}}

    Each mark_dirty() call atomically replaces one camera's complete entry
    set.  Because a tracking event is the authoritative snapshot of a single
    camera at an instant, this naturally evicts PHs that have left the field
    of view without needing a TTL.

    At publish time _flatten_phs() produces exactly one dot per person:

    - Identified persons (identity_id set): grouped by identity_id across
      all cameras.  When multiple cameras report the same person within
      _MULTI_CAM_WINDOW_S the calibrated floor positions are averaged;
      otherwise the most recently observed entry wins.

    - Anonymous persons (no identity_id): kept as individual ph_id entries.
      Cross-camera dedup for unknowns is the CTS world-tracker's job.

    A heartbeat fires every 5 s so the frontend does not flip to stale when
    the scene is static.
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
        # {camera_id: {ph_id: ph_data}} -- bounded by num_cameras x detections_per_frame
        self._camera_phs: dict[str, dict[str, dict[str, Any]]] = {}
        self._dirty = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_snapshot_id: str = ""

    def mark_dirty(self, camera_id: str, ph_data_list: list[dict[str, Any]]) -> None:
        """Replace camera_id's PH entries atomically and schedule a snapshot."""
        self._camera_phs[camera_id] = {
            ph["ph_id"]: ph for ph in ph_data_list if ph.get("ph_id")
        }
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

    def _flatten_phs(self) -> list[dict[str, Any]]:
        """Return exactly one entry per person across all cameras.

        Identified persons are grouped by identity_id; anonymous ones by ph_id.
        """
        # Collect all current observations from every camera.
        identified: dict[str, list[dict[str, Any]]] = {}  # identity_id → [ph_data, ...]
        anonymous: dict[str, dict[str, Any]] = {}          # ph_id → latest ph_data

        for cam_phs in self._camera_phs.values():
            for ph in cam_phs.values():
                identity_id = ph.get("identity_id")
                ph_id = ph.get("ph_id", "")
                if identity_id:
                    identified.setdefault(identity_id, []).append(ph)
                elif ph_id:
                    prev = anonymous.get(ph_id)
                    if prev is None or (ph.get("last_observed_at") or "") >= (prev.get("last_observed_at") or ""):
                        anonymous[ph_id] = ph

        result: list[dict[str, Any]] = list(anonymous.values())

        for observations in identified.values():
            if len(observations) == 1:
                result.append(observations[0])
                continue

            # When multiple cameras see the same person, average positions that
            # are within _MULTI_CAM_WINDOW_S of the most recent observation.
            latest_ts = _ts(max(o.get("last_observed_at") or "" for o in observations))
            if latest_ts is None:
                result.append(max(observations, key=lambda o: o.get("last_observed_at") or ""))
                continue

            recent = [
                o for o in observations
                if (t := _ts(o.get("last_observed_at"))) is not None
                and (latest_ts - t).total_seconds() <= _MULTI_CAM_WINDOW_S
            ]
            result.append(_average_observations(recent or observations))

        return result

    async def _publish(self) -> None:
        inferred_rooms = await self._fetch_inferred_rooms()
        phs = self._flatten_phs()

        try:
            content = json.dumps({"phs": phs, "rooms": inferred_rooms}, sort_keys=True, default=str)
            snapshot_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
            logger.warning("inferred_rooms_fetch_failed")
            return []
