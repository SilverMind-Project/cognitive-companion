"""HTTP client for the semantic-memory-service trend API.

Follows the same pattern as :mod:`backend.integrations.scene_analysis_client`:
configured from ``settings.yaml``, returns ``None`` / empty structures on
any failure so callers never need to handle exceptions.

Settings keys (under ``semantic_memory``)::

    semantic_memory:
      url: "http://localhost:8300"
      enabled: true
      timeout: 10

All result dataclasses map 1-to-1 to the service's Pydantic response
models so the cognitive-companion backend never needs to import from the
semantic-memory-service package directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.time import UTC

logger = get_logger(__name__)
_PayloadModel = TypeVar("_PayloadModel", bound=BaseModel)


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


class _RoomTrendPayload(BaseModel):
    room_id: str = ""
    room_name: str | None = None
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    baseline_available: bool = False
    clutter_score: float = 0.0
    trend_direction: str = "stable"
    overall_severity: str = "ok"
    persistent_objects: list[str] = Field(default_factory=list)
    novel_objects: list[str] = Field(default_factory=list)
    anomalies: list[dict] = Field(default_factory=list)

    @field_validator("as_of", mode="before")
    @classmethod
    def _parse_as_of(cls, value: object) -> datetime:
        return _coerce_datetime(value)

    @field_validator("persistent_objects", "novel_objects", mode="before")
    @classmethod
    def _parse_string_lists(cls, value: object) -> list[str]:
        return _coerce_string_list(value)

    @field_validator("anomalies", mode="before")
    @classmethod
    def _parse_anomalies(cls, value: object) -> list[dict]:
        return _coerce_dict_list(value)

    def to_result(self, *, fallback_room_id: str, raw: dict) -> RoomTrendResult:
        return RoomTrendResult(
            room_id=self.room_id or fallback_room_id,
            room_name=self.room_name,
            as_of=self.as_of,
            baseline_available=self.baseline_available,
            clutter_score=self.clutter_score,
            trend_direction=self.trend_direction,
            overall_severity=self.overall_severity,
            persistent_objects=self.persistent_objects,
            novel_objects=self.novel_objects,
            anomalies=self.anomalies,
            raw=raw,
        )


class _TrendSnapshotPayload(BaseModel):
    room_id: str = ""
    period_start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    unique_object_count: int = 0
    object_counts: dict[str, int] = Field(default_factory=dict)
    persistent_objects: list[str] = Field(default_factory=list)
    novel_objects: list[str] = Field(default_factory=list)
    embedding_variance: float = 0.0

    @field_validator("period_start", mode="before")
    @classmethod
    def _parse_period_start(cls, value: object) -> datetime:
        return _coerce_datetime(value)

    @field_validator("object_counts", mode="before")
    @classmethod
    def _parse_object_counts(cls, value: object) -> dict[str, int]:
        return _coerce_str_int_dict(value)

    @field_validator("persistent_objects", "novel_objects", mode="before")
    @classmethod
    def _parse_string_lists(cls, value: object) -> list[str]:
        return _coerce_string_list(value)

    def to_result(self, *, fallback_room_id: str) -> TrendSnapshot:
        return TrendSnapshot(
            room_id=self.room_id or fallback_room_id,
            period_start=self.period_start,
            unique_object_count=self.unique_object_count,
            object_counts=self.object_counts,
            persistent_objects=self.persistent_objects,
            novel_objects=self.novel_objects,
            embedding_variance=self.embedding_variance,
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ObjectTrendClient:
    """HTTP client for the semantic-memory-service trend API.

    Designed for graceful degradation: all methods return None or [] when
    the service is unreachable or not configured. Never raises to callers.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._base_url: str = (
            base_url if base_url is not None else settings.get_required("semantic_memory.url")
        ).rstrip("/")
        self._timeout: float = float(
            timeout if timeout is not None else settings.get_required("semantic_memory.timeout")
        )
        self.enabled: bool = (
            bool(enabled)
            if enabled is not None
            else bool(settings.get_required("semantic_memory.enabled"))
        )

    @property
    def configured(self) -> bool:
        """Whether the client has a valid base URL and is enabled."""
        return bool(self._base_url) and self.enabled

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
        payload = _validate_payload(
            data,
            _RoomTrendPayload,
            log_event="object_trend_get_room_invalid_payload",
            room_id=room_id,
        )
        return payload.to_result(fallback_room_id=room_id, raw=data) if payload else None

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
        for payload, raw in _validate_payload_list(
            items,
            _RoomTrendPayload,
            log_event="object_trend_get_all_invalid_payload",
        ):
            results.append(payload.to_result(fallback_room_id="", raw=raw))
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
        for payload, _raw in _validate_payload_list(
            items,
            _TrendSnapshotPayload,
            log_event="object_trend_get_snapshots_invalid_payload",
            room_id=room_id,
        ):
            snapshots.append(payload.to_result(fallback_room_id=room_id))
        return snapshots


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
    return datetime.now(UTC)
def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _coerce_dict_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _coerce_str_int_dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}

    parsed: dict[str, int] = {}
    for key, raw_count in value.items():
        if not isinstance(key, str):
            continue
        try:
            parsed[key] = int(raw_count)
        except (TypeError, ValueError):
            continue
    return parsed


def _validate_payload(
    data: object,
    model_cls: type[_PayloadModel],
    *,
    log_event: str,
    room_id: str | None = None,
) -> _PayloadModel | None:
    try:
        return model_cls.model_validate(data)
    except ValidationError:
        log_kwargs: dict[str, object] = {}
        if room_id is not None:
            log_kwargs["room_id"] = room_id
        logger.warning(log_event, **log_kwargs)
        return None


def _validate_payload_list(
    raw_items: object,
    model_cls: type[_PayloadModel],
    *,
    log_event: str,
    room_id: str | None = None,
) -> list[tuple[_PayloadModel, dict]]:
    if not isinstance(raw_items, list):
        log_kwargs: dict[str, object] = {}
        if room_id is not None:
            log_kwargs["room_id"] = room_id
        logger.warning(log_event, **log_kwargs)
        return []

    validated: list[tuple[_PayloadModel, dict]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            validated.append((model_cls.model_validate(item), item))
        except ValidationError:
            continue
    return validated
