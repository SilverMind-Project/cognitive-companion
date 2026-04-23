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
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)


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

        # Validate required fields.
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
