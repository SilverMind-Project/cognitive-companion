"""Publishes face-anchor-equivalent assertions to cc.identity_assertions.

When the recamera VLM path or any other CC-side identification identifies
a person, this publisher emits a message to the Redis stream so the
tracking-orchestrator can use the assertion as evidence in its Bayesian
identity resolver.  This is the bidirectional identity flow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger

logger = get_logger(__name__)

STREAM = "cc.identity_assertions"


class IdentityAssertionPublisher:
    """Publishes identity assertions to the cc.identity_assertions Redis stream."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def publish(
        self,
        person_id: str,
        confidence: float,
        camera_id: str = "",
        captured_at: datetime | None = None,
        floor_x_m: float = 0.0,
        floor_y_m: float = 0.0,
    ) -> None:
        """Publish a person-identity assertion.

        Args:
            person_id: The enrolled identity ID.
            confidence: Confidence score (0-1).
            camera_id: Which camera produced the identification.
            captured_at: When the identification was made.
            floor_x_m, floor_y_m: Floor coordinates in metres.
        """
        if captured_at is None:
            captured_at = datetime.now(UTC)

        fields = {
            "person_id": str(person_id),
            "confidence": str(confidence),
            "camera_id": str(camera_id),
            "captured_at": captured_at.isoformat(),
            "floor_x_m": str(floor_x_m),
            "floor_y_m": str(floor_y_m),
        }
        try:
            await self._redis.xadd(STREAM, fields)
            logger.debug(
                "identity_assertion_published",
                person_id=str(person_id),
                confidence=round(confidence, 3),
                camera_id=str(camera_id),
            )
        except Exception:
            logger.exception(
                "identity_assertion_publish_failed",
                person_id=str(person_id),
            )
