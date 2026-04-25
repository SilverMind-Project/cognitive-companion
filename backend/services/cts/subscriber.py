"""DementiaSignalSubscriber: Redis Streams consumer for tracking.signals.

This subscriber consumes ``DementiaSignal`` messages from the
``tracking.signals`` Redis Stream, persists them via :class:`SignalStore`,
and fires an event into the pipeline so existing rule-engine plumbing
can match on signal type.

Architecture
------------
The subscriber reuses the shared :class:`StreamConsumer` base class
(defined in :mod:`backend.services.cts.stream_consumer`) so each
subscriber is ~60 lines of actual logic.  Tests inject a fake Redis
via :class:`redis.asyncio.Redis` mock.

Field-name mapping
------------------
The orchestrator's ``SignalPublisher`` serializes using the orchestrator's
domain names (``identity_id``, ``signal_kind``, ``context``).  The CC
``SignalStore`` uses the CC-side names (``person_id``, ``signal_type``,
``context_json``).  This subscriber maps between the two namespaces so
both sides remain consistent with their own domain models.
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Field mapping: orchestrator publisher → CC subscriber
#
# The orchestrator's SignalPublisher._serialize() emits:
#   identity_id, signal_kind, context, severity, value, baseline,
#   z_score, window_start, window_end, emitted_at, signal_id
#
# The CC's SignalStore.insert() expects:
#   person_id, signal_type, context_json, severity, value, baseline,
#   z_score, window_start, window_end
# ---------------------------------------------------------------------------

# Required fields that MUST be present in the publisher payload.
# Uses the orchestrator's field names.
_REQUIRED_PUBLISHER_FIELDS = {"identity_id", "signal_kind", "severity", "window_start", "window_end", "value"}


class DementiaSignalSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``tracking.signals`` and persist each signal.

    Parameters
    ----------
    redis_url:
        Redis connection URL.
    consumer_id:
        Unique ID for this consumer instance (typically ``socket.gethostname()``).
    store:
        :class:`SignalStore` instance for database persistence.
    pipeline:
        Optional :class:`PipelineExecutor` (or compatible) for firing
        events into the rule engine.  Pass ``None`` if the pipeline
        is not available (e.g. during tests).
    """

    STREAM = "tracking.signals"
    GROUP = "cognitive-companion-signals"

    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        store: SignalStore,
        pipeline: Any | None = None,
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

    def decode(self, message_id: bytes, fields: dict) -> dict[str, Any] | None:
        """Parse raw Redis Stream fields into a signal dict.

        The publisher sends a single ``signal`` field containing a
        JSON-encoded dict.  Field names are mapped from orchestrator
        conventions to CC conventions before validation.

        Returns ``None`` to drop+ack malformed messages.
        """
        raw = fields.get(b"signal")
        if raw is None:
            return None

        # Try JSON first (primary format for now; proto can be added later).
        try:
            import json

            signal_data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("dementia_signal_parse_error", message_id=message_id)
            return None

        # Map orchestrator field names → CC field names.
        # Accept both naming conventions for forward/backward compatibility.
        signal_data = _map_field_names(signal_data)

        # Validate required fields (using CC-canonical names after mapping).
        required = {"person_id", "signal_type", "severity", "window_start", "window_end", "value"}
        if not required.issubset(signal_data):
            logger.warning(
                "dementia_signal_missing_fields",
                message_id=message_id,
                missing=required - set(signal_data.keys()),
            )
            return None

        return signal_data

    async def handle(self, signal: dict[str, Any]) -> bool:
        """Persist the signal and optionally fire a pipeline event.

        Returns ``True`` to ack the message, ``False`` to leave it pending.
        """
        try:
            signal_id = await self._store.insert(signal)
            logger.info(
                "dementia_signal_stored",
                signal_id=signal_id,
                signal_type=signal["signal_type"],
                person_id=signal["person_id"],
                severity=signal["severity"],
            )

            # Fire event into the rule engine if available.
            if self._pipeline is not None:
                try:
                    await self._pipeline.fire_event(
                        source="cts",
                        kind="dementia_signal",
                        payload={
                            "signal_id": signal_id,
                            "signal_kind": signal["signal_type"],
                            "person_id": signal["person_id"],
                            "severity": signal["severity"],
                            "window_start": signal["window_start"],
                            "window_end": signal["window_end"],
                            "evidence": signal.get("context_json", {}),
                        },
                    )
                except Exception:
                    logger.exception("dementia_signal_pipeline_fire_error")

        except Exception:
            logger.exception("dementia_signal_handle_error")
            return False

        return True


def _map_field_names(data: dict[str, Any]) -> dict[str, Any]:
    """Map orchestrator field names to CC field names.

    Orchestrator sends: ``identity_id``, ``signal_kind``, ``context``
    CC expects:         ``person_id``,   ``signal_type``,  ``context_json``

    Both naming conventions are accepted for compatibility.  If both are
    present the orchestrator name wins (it's the canonical source).
    """
    mapped = dict(data)

    # identity_id → person_id
    if "identity_id" in mapped and "person_id" not in mapped:
        mapped["person_id"] = mapped.pop("identity_id")
    elif "identity_id" in mapped:
        mapped.pop("identity_id")

    # signal_kind → signal_type
    if "signal_kind" in mapped and "signal_type" not in mapped:
        mapped["signal_type"] = mapped.pop("signal_kind")
    elif "signal_kind" in mapped:
        mapped.pop("signal_kind")

    # context → context_json
    if "context" in mapped and "context_json" not in mapped:
        mapped["context_json"] = mapped.pop("context")
    elif "context" in mapped:
        mapped.pop("context")

    return mapped
