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
from backend.integrations.proto.continuoustracking.v1.tracking_pb2 import (
    CCIdentityAssertion,
)

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
        raw_similarity: float = 0.0,
        calibrated_confidence: float | None = None,
        calibration_status: str = "uncalibrated",
        source: str = "cc-vlm",
        model_version: str = "v1",
        preprocessing_version: str = "v1",
    ) -> None:
        """Publish a person-identity assertion.

        Args:
            person_id: The enrolled identity ID.
            confidence: Confidence score (0-1).
            camera_id: Which camera produced the identification.
            captured_at: When the identification was made.
            floor_x_m, floor_y_m: Floor coordinates in metres.
            raw_similarity: Raw cosine similarity from the face ID service.
            calibrated_confidence: Calibrated confidence, if calibration is enabled.
            calibration_status: Status of the calibration ("calibrated", "uncalibrated", "extrapolated").
            source: The component that generated this assertion (e.g., "cc-arcface").
            model_version: Which model version was used.
            preprocessing_version: Which preprocessing version was used.
        """
        if captured_at is None:
            captured_at = datetime.now(UTC)

        msg = CCIdentityAssertion(
            person_id=str(person_id),
            camera_id=str(camera_id),
            captured_at_unix_ns=int(captured_at.timestamp() * 1e9),
            floor_x_m=float(floor_x_m),
            floor_y_m=float(floor_y_m),
            raw_similarity=float(raw_similarity),
            calibration_status=str(calibration_status),
            source=str(source),
            model_version=str(model_version),
            preprocessing_version=str(preprocessing_version),
        )
        if calibrated_confidence is not None:
            msg.calibrated_confidence = float(calibrated_confidence)

        fields = {b"assertion": msg.SerializeToString()}

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
