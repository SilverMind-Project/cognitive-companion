"""DementiaSignalSubscriber: Redis Streams consumer for tracking.signals.

Decodes ``DementiaSignal`` proto messages from the ``tracking.signals``
Redis Stream, persists them via :class:`SignalStore`, and fires an event
into the pipeline so existing rule-engine plumbing can match on signal
type.

Wire format: each Redis Streams message is a single field ``signal``
carrying the raw protobuf body of a
``continuoustracking.v1.DementiaSignal``.
"""

from __future__ import annotations

import json
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.proto.continuoustracking.v1 import signals_pb2
from backend.services.cts import metrics
from backend.services.cts._time import ns_to_iso
from backend.services.cts._types import PipelineExecutor
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)

FIELD = b"signal"


# Proto enum -> CC-canonical string. CC tables and filters key on the
# string form (matches the orchestrator's domain Literal aliases) so this
# subscriber is the single point of translation.

_PROTO_KIND_TO_STR: dict[int, str] = {
    signals_pb2.DEMENTIA_SIGNAL_KIND_PACING: "pacing",
    signals_pb2.DEMENTIA_SIGNAL_KIND_SUNDOWNING_INDEX: "sundowning_index",
    signals_pb2.DEMENTIA_SIGNAL_KIND_BATHROOM_DWELL_ANOMALY: "bathroom_dwell_anomaly",
    signals_pb2.DEMENTIA_SIGNAL_KIND_NIGHTTIME_MOVEMENT: "nighttime_movement",
    signals_pb2.DEMENTIA_SIGNAL_KIND_STILLNESS_ANOMALY: "stillness_anomaly",
    signals_pb2.DEMENTIA_SIGNAL_KIND_ABSENCE: "absence",
}

_PROTO_SEVERITY_TO_STR: dict[int, str] = {
    signals_pb2.DEMENTIA_SIGNAL_SEVERITY_INFO: "info",
    signals_pb2.DEMENTIA_SIGNAL_SEVERITY_WARNING: "warning",
    signals_pb2.DEMENTIA_SIGNAL_SEVERITY_EMERGENCY: "emergency",
}


class DementiaSignalSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``tracking.signals`` and persist each signal."""

    STREAM = "tracking.signals"
    GROUP = "cognitive-companion-signals"

    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        store: SignalStore,
        pipeline: PipelineExecutor | None = None,
    ) -> None:
        super().__init__(
            ConsumerConfig(
                redis_url=redis_url,
                stream=self.STREAM,
                group=self.GROUP,
                consumer_id=consumer_id,
                concurrency=1,
            )
        )
        self._store = store
        self._pipeline = pipeline

    # -- StreamConsumer abstract methods -------------------------------------

    def decode(self, message_id: bytes, fields: dict[bytes | str, bytes | str]) -> dict[str, Any] | None:
        """Decode the proto envelope into the SignalStore dict shape."""
        payload = fields.get(FIELD) or fields.get(FIELD.decode())
        if payload is None:
            return None
        if isinstance(payload, str):
            payload = payload.encode("latin-1")

        try:
            message = signals_pb2.DementiaSignal.FromString(payload)
        except Exception:
            logger.warning("dementia_signal_proto_decode_error", message_id=message_id)
            metrics.cts_signals_decode_errors.inc()
            return None

        kind = _PROTO_KIND_TO_STR.get(message.kind)
        severity = _PROTO_SEVERITY_TO_STR.get(message.severity)
        if not kind or not severity or not message.identity_id:
            logger.warning(
                "dementia_signal_missing_fields",
                message_id=message_id,
                kind=message.kind,
                severity=message.severity,
                identity_id=message.identity_id,
            )
            return None

        try:
            context = json.loads(message.context_json) if message.context_json else {}
            if not isinstance(context, dict):
                context = {}
        except json.JSONDecodeError:
            logger.warning("dementia_signal_context_not_json", raw=message.context_json[:64])
            context = {}

        return {
            "signal_id": message.signal_id,
            "person_id": message.identity_id,
            "signal_type": kind,
            "severity": severity,
            "value": message.value,
            "baseline": message.baseline if message.has_baseline else None,
            "z_score": message.z_score if message.has_z_score else None,
            "window_start": ns_to_iso(message.window_start_unix_ns),
            "window_end": ns_to_iso(message.window_end_unix_ns),
            "context_json": context,
            "algorithm_version": message.algorithm_version if message.algorithm_version else None,
        }

    async def handle(self, signal: dict[str, Any]) -> bool:
        kind = signal.get("signal_type", "unknown")
        metrics.cts_signals_received.labels(signal_kind=kind).inc()

        try:
            row_id, action = await self._store.upsert(signal)

            if action == "update":
                logger.debug(
                    "dementia_signal_upsert_noop",
                    signal_id=signal.get("signal_id"),
                    signal_type=kind,
                    severity=signal["severity"],
                    action=action,
                )
                metrics.cts_signals_persisted.labels(signal_kind=kind).inc()
                return True

            logger.info(
                "dementia_signal_stored",
                row_id=row_id,
                signal_id=signal.get("signal_id"),
                signal_type=kind,
                person_id=signal["person_id"],
                severity=signal["severity"],
                action=action,
            )
            metrics.cts_signals_persisted.labels(signal_kind=kind).inc()

            # Only fire pipeline events for new signals or severity escalations.
            # Re-upserts at equal/lower severity do NOT re-trigger notifications.
            if self._pipeline is not None:
                try:
                    await self._pipeline.fire_event(
                        source="cts",
                        kind="dementia_signal",
                        payload={
                            "row_id": row_id,
                            "signal_id": signal.get("signal_id"),
                            "signal_kind": kind,
                            "person_id": signal["person_id"],
                            "severity": signal["severity"],
                            "window_start": signal["window_start"],
                            "window_end": signal["window_end"],
                            "action": action,
                            "evidence": signal.get("context_json", {}),
                        },
                    )
                except Exception:
                    logger.exception("dementia_signal_pipeline_fire_error")
        except Exception:
            logger.exception("dementia_signal_handle_error")
            metrics.cts_signals_dropped.labels(signal_kind=kind).inc()
            return False

        return True



