"""TrackingResponseSubscriber: drain tracking.responses (FrameResponse protos).

This is a dead-letter drain -- the stream carries per-frame pipeline outcomes
published by tracking-orchestrator.  CC does not act on these records; it
consumes them so they do not accumulate in the PEL and so operators can read
latency / error-rate metrics from Prometheus.

``handle()`` always returns True so every message is immediately ACK-ed.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.integrations.proto.continuoustracking.v1 import frame_pb2
from backend.services.cts import metrics
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)

FIELD = b"response"


class TrackingResponseSubscriber(StreamConsumer[frame_pb2.FrameResponse]):
    """Consume ``tracking.responses`` and emit Prometheus metrics."""

    STREAM = "tracking.responses"
    GROUP = "cognitive-companion-responses"

    def __init__(self, redis_url: str, consumer_id: str) -> None:
        super().__init__(
            ConsumerConfig(
                redis_url=redis_url,
                stream=self.STREAM,
                group=self.GROUP,
                consumer_id=consumer_id,
                concurrency=2,
            )
        )

    # -- StreamConsumer abstract methods ---------------------------------------

    def decode(
        self,
        message_id: bytes,
        fields: dict[bytes | str, bytes | str],
    ) -> frame_pb2.FrameResponse | None:
        payload = fields.get(FIELD) or fields.get(FIELD.decode())
        if payload is None:
            logger.warning("tracking_response_missing_payload", message_id=message_id)
            metrics.cts_tracking_responses_decode_errors.inc()
            return None
        if isinstance(payload, str):
            payload = payload.encode("latin-1")

        try:
            return frame_pb2.FrameResponse.FromString(payload)
        except Exception:
            logger.exception("tracking_response_proto_decode_error", message_id=message_id)
            metrics.cts_tracking_responses_decode_errors.inc()
            return None

    async def handle(self, response: frame_pb2.FrameResponse) -> bool:
        outcome = "success" if response.success else (response.error_code or "processing_error")
        metrics.cts_tracking_responses_received.labels(outcome=outcome).inc()
        logger.debug(
            "tracking_response_received",
            camera_id=response.camera_id,
            frame_index=response.frame_index,
            success=response.success,
            error_code=response.error_code or None,
            latency_us=response.processing_latency_us,
        )
        return True
