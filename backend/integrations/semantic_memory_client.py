"""HTTP client for the semantic-memory-service.

Covers every public endpoint of the service: observations, movements,
object presence, trends, and health.  Designed for graceful degradation:
all methods return ``None``, ``[]``, or a typed zero-value dataclass
when the service is unreachable or not configured.

Settings keys (under ``semantic_memory``)::

    semantic_memory:
      url: "http://localhost:8300"
      enabled: true
      timeout: 10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.core.logging import get_logger
from backend.core.time import normalize_utc_datetime

from ._http_base import HttpUpstreamClient

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Frozen result dataclasses (public API surface)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservationCreate:
    """Input to create_observation."""

    room_id: str | None = None
    description: str = ""
    object_list: list[str] = field(default_factory=list)
    hazard_flags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    source: str = "scene_intel"
    # DL-M05: attributes an observation to a resident and distinguishes
    # record taxonomy ("scene" / "guided_episode" / "hygiene_verdict").
    person_id: str | None = None
    kind: str | None = None
    # 768-dim text embedding (embeddinggemma), distinct from ``embedding``
    # (CLIP image embedding); SMS keeps these in separate columns so text
    # search never mixes with image-similarity search.
    description_embedding: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class ObservationRecord:
    """Returned by create_observation."""

    id: int
    room_id: str
    description: str
    object_list: list[str]
    hazard_flags: list[str]
    observed_at: datetime
    source: str
    created_at: datetime
    person_id: str | None = None
    kind: str | None = None


@dataclass(frozen=True)
class ObservationSearchRequest:
    """Input to search_observations."""

    room_id: str | None = None
    since_minutes: int | None = 60
    objects_any: list[str] = field(default_factory=list)
    hazard_flags_any: list[str] = field(default_factory=list)
    query_text: str = ""
    limit: int = 5
    person_id: str | None = None
    # "scene" also matches legacy rows written before this column existed.
    kind: str | None = None


@dataclass(frozen=True)
class ObservationSearchHit:
    """Returned by search_observations."""

    id: int
    room_id: str
    observed_at: datetime
    description: str
    object_list: list[str]
    hazard_flags: list[str]
    text_similarity: float = 0.0
    image_similarity: float = 0.0
    source: str = ""
    person_id: str | None = None
    kind: str | None = None


@dataclass(frozen=True)
class MovementCreate:
    """Input to create_movement."""

    person_id: str
    from_room_id: str
    to_room_id: str
    direction_semantic: str = "any"
    confidence: float = 0.8
    observation_id: int | None = None


@dataclass(frozen=True)
class MovementRecord:
    """Returned by create_movement."""

    id: int
    person_id: str
    from_room_id: str
    to_room_id: str
    direction_semantic: str
    confidence: float
    observed_at: datetime
    observation_id: int | None = None


@dataclass(frozen=True)
class MovementTransitionRecord:
    """Returned by get_transitions."""

    id: int
    person_id: str
    from_room_id: str
    to_room_id: str
    direction_semantic: str
    confidence: float
    observed_at: datetime
    observation_id: int | None = None


@dataclass(frozen=True)
class ObjectPresenceRecord:
    """Returned by get_recent_objects."""

    label: str
    observation_count: int
    last_seen_at: datetime


@dataclass(frozen=True)
class RoomTrendResult:
    """Returned by get_room_trends / get_all_room_trends."""

    room_id: str
    room_name: str | None
    as_of: datetime
    baseline_available: bool
    clutter_score: float
    trend_direction: str
    overall_severity: str
    persistent_objects: list[str] = field(default_factory=list)
    novel_objects: list[str] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ObservationsByDay:
    """One day/source bucket, part of WriteHealthResult."""

    day: datetime
    source: str
    count: int


@dataclass(frozen=True)
class WriteHealthResult:
    """Returned by get_write_health."""

    last_observation_at: datetime | None
    last_movement_at: datetime | None
    observations_by_day: list[ObservationsByDay] = field(default_factory=list)
    total_observations: int = 0
    total_movements: int = 0


@dataclass(frozen=True)
class TrendSnapshot:
    """Returned by get_snapshots."""

    room_id: str
    period_start: datetime
    unique_object_count: int
    object_counts: dict[str, int] = field(default_factory=dict)
    persistent_objects: list[str] = field(default_factory=list)
    novel_objects: list[str] = field(default_factory=list)
    embedding_variance: float = 0.0


# ---------------------------------------------------------------------------
# Pydantic wire-level payloads (private)
# ---------------------------------------------------------------------------


class _ObservationPayload(BaseModel):
    id: int = 0
    room_id: str = ""
    description: str = ""
    object_list: list[str] = Field(default_factory=list)
    hazard_flags: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "scene_intel"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    person_id: str | None = None
    kind: str | None = None

    @field_validator("observed_at", "created_at", mode="before")
    @classmethod
    def _parse_observed(cls, value: object) -> datetime:
        dt = normalize_utc_datetime(_coerce_datetime(value))
        assert dt is not None
        return dt

    @field_validator("object_list", "hazard_flags", mode="before")
    @classmethod
    def _parse_lists(cls, value: object) -> list[str]:
        return _coerce_string_list(value)

    def to_record(self) -> ObservationRecord:
        return ObservationRecord(
            id=self.id,
            room_id=self.room_id,
            description=self.description,
            object_list=self.object_list,
            hazard_flags=self.hazard_flags,
            observed_at=self.observed_at,
            source=self.source,
            created_at=self.created_at,
            person_id=self.person_id,
            kind=self.kind,
        )


class _ObservationSearchHitPayload(BaseModel):
    id: int = 0
    room_id: str = ""
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    description: str = ""
    object_list: list[str] = Field(default_factory=list)
    hazard_flags: list[str] = Field(default_factory=list)
    text_similarity: float = 0.0
    image_similarity: float = 0.0
    source: str = ""
    person_id: str | None = None
    kind: str | None = None

    @field_validator("observed_at", mode="before")
    @classmethod
    def _parse_observed(cls, value: object) -> datetime:
        dt = normalize_utc_datetime(_coerce_datetime(value))
        assert dt is not None
        return dt

    @field_validator("object_list", "hazard_flags", mode="before")
    @classmethod
    def _parse_lists(cls, value: object) -> list[str]:
        return _coerce_string_list(value)

    def to_hit(self) -> ObservationSearchHit:
        return ObservationSearchHit(
            id=self.id,
            room_id=self.room_id,
            observed_at=self.observed_at,
            description=self.description,
            object_list=self.object_list,
            hazard_flags=self.hazard_flags,
            text_similarity=self.text_similarity,
            image_similarity=self.image_similarity,
            source=self.source,
            person_id=self.person_id,
            kind=self.kind,
        )


class _MovementPayload(BaseModel):
    id: int = 0
    person_id: str = ""
    from_room_id: str = ""
    to_room_id: str = ""
    direction_semantic: str = "any"
    confidence: float = 0.8
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    observation_id: int | None = None

    @field_validator("observed_at", mode="before")
    @classmethod
    def _parse_observed(cls, value: object) -> datetime:
        dt = normalize_utc_datetime(_coerce_datetime(value))
        assert dt is not None
        return dt

    def to_record(self) -> MovementRecord:
        return MovementRecord(
            id=self.id,
            person_id=self.person_id,
            from_room_id=self.from_room_id,
            to_room_id=self.to_room_id,
            direction_semantic=self.direction_semantic,
            confidence=self.confidence,
            observed_at=self.observed_at,
            observation_id=self.observation_id,
        )

    def to_transition(self) -> MovementTransitionRecord:
        return MovementTransitionRecord(
            id=self.id,
            person_id=self.person_id,
            from_room_id=self.from_room_id,
            to_room_id=self.to_room_id,
            direction_semantic=self.direction_semantic,
            confidence=self.confidence,
            observed_at=self.observed_at,
            observation_id=self.observation_id,
        )


class _ObjectPresencePayload(BaseModel):
    label: str = ""
    observation_count: int = 0
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("last_seen_at", mode="before")
    @classmethod
    def _parse_last_seen(cls, value: object) -> datetime:
        dt = normalize_utc_datetime(_coerce_datetime(value))
        assert dt is not None
        return dt

    def to_record(self) -> ObjectPresenceRecord:
        return ObjectPresenceRecord(
            label=self.label,
            observation_count=self.observation_count,
            last_seen_at=self.last_seen_at,
        )


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
        dt = normalize_utc_datetime(_coerce_datetime(value))
        assert dt is not None
        return dt

    @field_validator("persistent_objects", "novel_objects", mode="before")
    @classmethod
    def _parse_lists(cls, value: object) -> list[str]:
        return _coerce_string_list(value)

    @field_validator("anomalies", mode="before")
    @classmethod
    def _parse_anomalies(cls, value: object) -> list[dict]:
        return _coerce_dict_list(value)

    def to_result(self) -> RoomTrendResult:
        return RoomTrendResult(
            room_id=self.room_id,
            room_name=self.room_name,
            as_of=self.as_of,
            baseline_available=self.baseline_available,
            clutter_score=self.clutter_score,
            trend_direction=self.trend_direction,
            overall_severity=self.overall_severity,
            persistent_objects=self.persistent_objects,
            novel_objects=self.novel_objects,
            anomalies=self.anomalies,
        )


class _ObservationsByDayPayload(BaseModel):
    day: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = ""
    count: int = 0

    @field_validator("day", mode="before")
    @classmethod
    def _parse_day(cls, value: object) -> datetime:
        dt = normalize_utc_datetime(_coerce_datetime(value))
        assert dt is not None
        return dt

    def to_bucket(self) -> ObservationsByDay:
        return ObservationsByDay(day=self.day, source=self.source, count=self.count)


class _WriteHealthPayload(BaseModel):
    last_observation_at: datetime | None = None
    last_movement_at: datetime | None = None
    observations_by_day: list[_ObservationsByDayPayload] = Field(default_factory=list)
    total_observations: int = 0
    total_movements: int = 0

    @field_validator("last_observation_at", "last_movement_at", mode="before")
    @classmethod
    def _parse_optional(cls, value: object) -> datetime | None:
        if value is None:
            return None
        dt = normalize_utc_datetime(_coerce_datetime(value))
        return dt

    def to_result(self) -> WriteHealthResult:
        return WriteHealthResult(
            last_observation_at=self.last_observation_at,
            last_movement_at=self.last_movement_at,
            observations_by_day=[b.to_bucket() for b in self.observations_by_day],
            total_observations=self.total_observations,
            total_movements=self.total_movements,
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
        dt = normalize_utc_datetime(_coerce_datetime(value))
        assert dt is not None
        return dt

    @field_validator("object_counts", mode="before")
    @classmethod
    def _parse_object_counts(cls, value: object) -> dict[str, int]:
        return _coerce_str_int_dict(value)

    @field_validator("persistent_objects", "novel_objects", mode="before")
    @classmethod
    def _parse_lists(cls, value: object) -> list[str]:
        return _coerce_string_list(value)

    def to_result(self) -> TrendSnapshot:
        return TrendSnapshot(
            room_id=self.room_id,
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


class SemanticMemoryClient(HttpUpstreamClient):
    """Async HTTP client for the semantic-memory-service.

    All public methods return ``None``, ``[]``, or a typed zero-value
    dataclass when the service is unavailable.  Never raises to callers.
    """

    SETTINGS_PREFIX = "semantic_memory"

    # -- Observations --------------------------------------------------------

    async def create_observation(self, obs: ObservationCreate) -> ObservationRecord | None:
        """POST /api/v1/observations."""
        body: dict[str, Any] = {
            "room_id": obs.room_id,
            "description": obs.description,
            "object_list": obs.object_list,
            "hazard_flags": obs.hazard_flags,
            "embedding": obs.embedding,
            # Empty list means "not computed"; send None so pgvector stores
            # NULL rather than rejecting a zero-length vector(768) value.
            "description_embedding": obs.description_embedding or None,
            "source": obs.source,
            "observed_at": datetime.now(UTC).isoformat(),
            "person_id": obs.person_id,
            "kind": obs.kind,
        }
        data = await self._post_json("/api/v1/observations", json=body)
        if data is None:
            return None
        payload = _validate_payload(data, _ObservationPayload)
        return payload.to_record() if payload else None

    async def search_observations(
        self, req: ObservationSearchRequest
    ) -> list[ObservationSearchHit]:
        """POST /api/v1/observations/search."""
        body: dict[str, Any] = {
            "room_id": req.room_id,
            "since_minutes": req.since_minutes,
            "objects_any": req.objects_any,
            "hazard_flags_any": req.hazard_flags_any,
            "query_text": req.query_text,
            "limit": req.limit,
            "person_id": req.person_id,
            "kind": req.kind,
        }
        data = await self._post_json("/api/v1/observations/search", json=body)
        if data is None:
            return []
        if not isinstance(data, list):
            return []
        hits: list[ObservationSearchHit] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            payload = _validate_payload(item, _ObservationSearchHitPayload)
            if payload:
                hits.append(payload.to_hit())
        return hits

    async def prune_observations(self, days: int) -> int:
        """DELETE /api/v1/observations/prune?days=N. Returns count or 0."""
        data = await self._delete_json("/api/v1/observations/prune", params={"days": days})
        if data is None:
            return 0
        if isinstance(data, dict):
            return int(data.get("pruned", 0))
        return 0

    # -- Movements -----------------------------------------------------------

    async def create_movement(self, movement: MovementCreate) -> MovementRecord | None:
        """POST /api/v1/movements."""
        body: dict[str, Any] = {
            "person_id": movement.person_id,
            "from_room_id": movement.from_room_id,
            "to_room_id": movement.to_room_id,
            "direction_semantic": movement.direction_semantic,
            "confidence": movement.confidence,
            "observation_id": movement.observation_id,
            "observed_at": datetime.now(UTC).isoformat(),
        }
        data = await self._post_json("/api/v1/movements", json=body)
        if data is None:
            return None
        payload = _validate_payload(data, _MovementPayload)
        return payload.to_record() if payload else None

    async def get_transitions(
        self,
        person_id: str,
        *,
        semantic: str | None = None,
        to_room_id: str | None = None,
        since_minutes: int | None = None,
    ) -> list[MovementTransitionRecord]:
        """GET /api/v1/movements/transitions?person_id=..."""
        params: dict[str, Any] = {"person_id": person_id}
        if semantic is not None:
            params["semantic"] = semantic
        if to_room_id is not None:
            params["to_room_id"] = to_room_id
        if since_minutes is not None:
            params["since_minutes"] = since_minutes
        data = await self._get_json("/api/v1/movements/transitions", params=params)
        if data is None:
            return []
        if not isinstance(data, list):
            return []
        transitions: list[MovementTransitionRecord] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            payload = _validate_payload(item, _MovementPayload)
            if payload:
                transitions.append(payload.to_transition())
        return transitions

    # -- Object presence -----------------------------------------------------

    async def get_recent_objects(
        self, room_id: str, since_minutes: int = 60
    ) -> list[ObjectPresenceRecord]:
        """GET /api/v1/objects/{room_id}/recent?since_minutes=..."""
        data = await self._get_json(
            f"/api/v1/objects/{room_id}/recent",
            params={"since_minutes": since_minutes},
        )
        if data is None:
            return []
        if not isinstance(data, list):
            return []
        records: list[ObjectPresenceRecord] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            payload = _validate_payload(item, _ObjectPresencePayload)
            if payload:
                records.append(payload.to_record())
        return records

    # -- Trends --------------------------------------------------------------

    async def get_room_trends(self, room_id: str) -> RoomTrendResult | None:
        """GET /api/v1/trends/{room_id}/current."""
        data = await self._get_json(f"/api/v1/trends/{room_id}/current")
        if data is None:
            return None
        payload = _validate_payload(data, _RoomTrendPayload)
        return payload.to_result() if payload else None

    async def get_all_room_trends(self) -> list[RoomTrendResult]:
        """GET /api/v1/trends/rooms."""
        data = await self._get_json("/api/v1/trends/rooms")
        if data is None:
            return []
        if not isinstance(data, list):
            return []
        results: list[RoomTrendResult] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            payload = _validate_payload(item, _RoomTrendPayload)
            if payload:
                results.append(payload.to_result())
        return results

    async def get_snapshots(self, room_id: str, since_hours: int = 24) -> list[TrendSnapshot]:
        """GET /api/v1/trends/{room_id}/snapshots?since_hours=N."""
        data = await self._get_json(
            f"/api/v1/trends/{room_id}/snapshots",
            params={"since_hours": since_hours},
        )
        if data is None:
            return []
        if not isinstance(data, list):
            return []
        snapshots: list[TrendSnapshot] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            payload = _validate_payload(item, _TrendSnapshotPayload)
            if payload:
                snapshots.append(payload.to_result())
        return snapshots

    # -- Health --------------------------------------------------------------

    async def health_check(self) -> dict | None:
        """GET /health. Returns the service health dict or None."""
        return await self._get_json("/health")

    async def get_write_health(self, days: int = 14) -> WriteHealthResult | None:
        """GET /api/v1/stats/write-health. Returns None when unreachable/unconfigured."""
        data = await self._get_json("/api/v1/stats/write-health", params={"days": days})
        if data is None:
            logger.warning("semantic_memory_write_health_unavailable")
            return None
        payload = _validate_payload(data, _WriteHealthPayload)
        return payload.to_result() if payload else None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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
        except TypeError, ValueError:
            continue
    return parsed


def _validate_payload[PayloadModelT: BaseModel](
    data: object,
    model_cls: type[PayloadModelT],
) -> PayloadModelT | None:
    try:
        return model_cls.model_validate(data)
    except ValidationError:
        logger.warning("semantic_memory_invalid_payload")
        return None
