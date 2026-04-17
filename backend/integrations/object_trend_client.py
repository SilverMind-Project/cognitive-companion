"""HTTP client for the semantic-memory-service trend API.

Follows the same pattern as ``scene_analysis_client``: configured from
``settings.yaml``, returns ``None`` / empty structures on any failure so
callers never need to handle exceptions.

Settings keys (under ``object_trends``)::

    object_trends:
      base_url: "http://localhost:8100"
      enabled: true
      timeout: 10

All result dataclasses map 1-to-1 to the service's Pydantic response
models so the cognitive-companion backend never needs to import from the
semantic-memory-service package directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx

from backend.core.logging import get_logger
from backend.core.time import UTC

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RoomTrendResult:
    """Typed result from GET /api/v1/trends/{room_id}/current."""

    room_id: str
    room_name: str | None
    as_of: datetime
    baseline_available: bool
    clutter_score: float  # z-score of latest unique_object_count
    trend_direction: str  # "increasing" | "decreasing" | "stable"
    overall_severity: str  # "ok" | "info" | "warning" | "critical"
    persistent_objects: list[str] = field(default_factory=list)
    novel_objects: list[str] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class TrendSnapshot:
    """One hourly snapshot row from the snapshots endpoint."""

    room_id: str
    period_start: datetime
    unique_object_count: int
    object_counts: dict[str, int] = field(default_factory=dict)
    persistent_objects: list[str] = field(default_factory=list)
    novel_objects: list[str] = field(default_factory=list)
    embedding_variance: float = 0.0


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ObjectTrendClient:
    """HTTP client for the semantic-memory-service trend API.

    Designed for graceful degradation: all methods return None or [] when
    the service is unreachable or not configured. Never raises to callers.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        """Whether the client has a valid base URL."""
        return bool(self._base_url)

    async def get_room_trends(self, room_id: str) -> RoomTrendResult | None:
        """GET /api/v1/trends/{room_id}/current.

        Returns None if service unreachable or room has no data yet.
        """
        if not self.configured:
            return None

        url = f"{self._base_url}/api/v1/trends/{room_id}/current"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("object_trend_get_room_error", room_id=room_id)
            return None

        as_of_str = data.get("as_of")
        as_of = datetime.fromisoformat(as_of_str) if as_of_str else datetime.now(UTC)

        return RoomTrendResult(
            room_id=data.get("room_id", room_id),
            room_name=data.get("room_name"),
            as_of=as_of,
            baseline_available=data.get("baseline_available", False),
            clutter_score=float(data.get("clutter_score", 0.0)),
            trend_direction=data.get("trend_direction", "stable"),
            overall_severity=data.get("overall_severity", "ok"),
            persistent_objects=data.get("persistent_objects", []),
            novel_objects=data.get("novel_objects", []),
            anomalies=data.get("anomalies", []),
            raw=data,
        )

    async def get_all_room_trends(self) -> list[RoomTrendResult]:
        """GET /api/v1/trends/rooms. Returns [] on error."""
        if not self.configured:
            return []

        url = f"{self._base_url}/api/v1/trends/rooms"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                items = resp.json()
        except Exception:
            logger.exception("object_trend_get_all_error")
            return []

        results: list[RoomTrendResult] = []
        for item in items:
            as_of_str = item.get("as_of")
            as_of = datetime.fromisoformat(as_of_str) if as_of_str else datetime.now(UTC)

            results.append(
                RoomTrendResult(
                    room_id=item.get("room_id", ""),
                    room_name=item.get("room_name"),
                    as_of=as_of,
                    baseline_available=item.get("baseline_available", False),
                    clutter_score=float(item.get("clutter_score", 0.0)),
                    trend_direction=item.get("trend_direction", "stable"),
                    overall_severity=item.get("overall_severity", "ok"),
                    persistent_objects=item.get("persistent_objects", []),
                    novel_objects=item.get("novel_objects", []),
                    anomalies=item.get("anomalies", []),
                    raw=item,
                )
            )
        return results

    async def get_snapshots(
        self, room_id: str, since_hours: int = 24
    ) -> list[TrendSnapshot]:
        """GET /api/v1/trends/{room_id}/snapshots?since_hours=N.

        Returns [] on error.
        """
        if not self.configured:
            return []

        url = f"{self._base_url}/api/v1/trends/{room_id}/snapshots"
        params = {"since_hours": since_hours}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                items = resp.json()
        except Exception:
            logger.exception("object_trend_get_snapshots_error", room_id=room_id)
            return []

        snapshots: list[TrendSnapshot] = []
        for item in items:
            period_start_str = item.get("period_start")
            if period_start_str:
                period_start = datetime.fromisoformat(period_start_str)
            else:
                period_start = datetime.now(UTC)

            snapshots.append(
                TrendSnapshot(
                    room_id=item.get("room_id", room_id),
                    period_start=period_start,
                    unique_object_count=int(item.get("unique_object_count", 0)),
                    object_counts=item.get("object_counts", {}),
                    persistent_objects=item.get("persistent_objects", []),
                    novel_objects=item.get("novel_objects", []),
                    embedding_variance=float(
                        item.get("embedding_variance", 0.0)
                    ),
                )
            )
        return snapshots
