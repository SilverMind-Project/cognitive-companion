"""Protocols for CTS-injected service dependencies.

Replaces ``Any``-typed service parameters throughout the CTS package with
structural :class:`Protocol` classes.  Each protocol defines only the
methods that CTS code actually calls — no unused methods, no over-specifying.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.orm import Session

from backend.services.cts.location_repository import LocationRepository

__all__ = [
    "ConnectionManager",
    "DBSessionFactory",
    "LocationRepository",
    "MinioClient",
    "PipelineExecutor",
    "SceneAnalysisClient",
    "SemanticMemoryClient",
]


class ConnectionManager(Protocol):
    """WebSocket connection manager (subset used by CTS subscribers)."""

    async def broadcast(self, payload: dict[str, Any]) -> None: ...

    async def disconnect(self, websocket: Any) -> None: ...


class PipelineExecutor(Protocol):
    """Pipeline event-firing interface used by CTS subscribers."""

    async def fire_event(
        self,
        *,
        source: str,
        kind: str,
        payload: dict[str, Any],
    ) -> None: ...


class MinioClient(Protocol):
    """MinIO client subset used by the scene-sample subscriber and frame router."""

    def generate_presigned_url(self, key: str, expiration: int) -> str: ...

    async def async_get_object(self, key: str) -> bytes | None: ...


class SceneAnalysisClient(Protocol):
    """Scene analysis service subset used by the scene-sample subscriber."""

    @property
    def configured(self) -> bool: ...

    async def analyze(
        self,
        image_bytes: bytes,
        *,
        run_detect: bool = False,
        run_describe: bool = False,
        run_embed: bool = False,
        run_hazards: bool = False,
        sensor_id: str = "",
    ) -> Any: ...


class SemanticMemoryClient(Protocol):
    """Semantic memory service subset used by the scene-sample subscriber."""

    @property
    def configured(self) -> bool: ...

    async def create_observation(self, observation: Any) -> Any | None: ...


# DBSessionFactory: callable that returns a new SQLAlchemy Session.
DBSessionFactory = Callable[[], Session]
