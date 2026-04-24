"""CTSRuntime: lifecycle manager for the three CTS subscribers.

A single owner so ``main.py`` lifespan does not grow three copies of the
same start/stop boilerplate. Constructing ``CTSRuntime`` does not start any
I/O; call :meth:`start` inside the lifespan and :meth:`stop` on shutdown.

If ``cts.enabled`` is ``False``, ``main.py`` never calls :meth:`start` - the
runtime object is not constructed, which keeps the feature-flag guarantee
that no CTS code executes when the flag is off.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from backend.core.logging import get_logger
from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber
from backend.services.cts.identity_rewriter import IdentityRewriter
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.source_authority import SourceAuthority
from backend.services.cts.subscriber import DementiaSignalSubscriber
from backend.services.cts.tracking_event_subscriber import TrackingEventSubscriber

logger = get_logger(__name__)


@dataclass
class CTSRuntimeConfig:
    """Runtime wiring for CTSRuntime.

    One instance per CC backend process.
    """

    redis_url: str
    consumer_id: str
    cts_lock_s: float = 60.0


@dataclass
class _SubscriberBundle:
    """Handle to one subscriber's state (subscriber + its background task)."""

    name: str
    subscriber: Any
    task: asyncio.Task[None] | None = None


class CTSRuntime:
    """Owns the three CTS subscribers and shared CTS services."""

    def __init__(
        self,
        *,
        config: CTSRuntimeConfig,
        db_factory,  # type: ignore[no-untyped-def]
        ws_manager: Any = None,
        pipeline: Any = None,
    ) -> None:
        self._cfg = config
        self._db_factory = db_factory
        self._ws_manager = ws_manager
        self._pipeline = pipeline

        authority = SourceAuthority(cts_lock_s=config.cts_lock_s)
        self.location_writer = LocationWriter(db_factory=db_factory, authority=authority)
        self.identity_rewriter = IdentityRewriter(
            db_factory=db_factory, ws_manager=ws_manager
        )
        self.signal_store = SignalStore(db_factory=db_factory)

        self.tracking_event_subscriber = TrackingEventSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
            writer=self.location_writer,
            ws_manager=ws_manager,
            pipeline=pipeline,
        )
        self.identity_revision_subscriber = IdentityRevisionSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
            rewriter=self.identity_rewriter,
            pipeline=pipeline,
        )
        self.dementia_signal_subscriber = DementiaSignalSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
            store=self.signal_store,
            pipeline=pipeline,
        )

        self._bundles: list[_SubscriberBundle] = [
            _SubscriberBundle(name="tracking_events", subscriber=self.tracking_event_subscriber),
            _SubscriberBundle(name="identity_revisions", subscriber=self.identity_revision_subscriber),
            _SubscriberBundle(name="dementia_signals", subscriber=self.dementia_signal_subscriber),
        ]

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Start all three subscribers as background tasks.

        Idempotent: calling start twice is a no-op on already-running tasks.
        """
        for bundle in self._bundles:
            if bundle.task is not None and not bundle.task.done():
                continue
            bundle.task = asyncio.create_task(
                bundle.subscriber.start(),
                name=f"cts-runtime-{bundle.name}",
            )
        logger.info(
            "cts_runtime_started",
            subscribers=[b.name for b in self._bundles],
            consumer_id=self._cfg.consumer_id,
        )

    async def stop(self) -> None:
        """Signal each subscriber to stop, then await graceful drain.

        Each subscriber owns its Redis connection; its ``stop()`` flips an
        event and :meth:`StreamConsumer.start` exits after the next tick.
        We wait up to 10 seconds per subscriber before cancelling hard.
        """
        for bundle in self._bundles:
            if bundle.subscriber is not None:
                try:
                    await bundle.subscriber.stop()
                except Exception:
                    logger.exception(
                        "cts_runtime_subscriber_stop_error", name=bundle.name
                    )

        for bundle in self._bundles:
            if bundle.task is None:
                continue
            try:
                await asyncio.wait_for(bundle.task, timeout=10.0)
            except TimeoutError as exc:
                logger.warning(
                    "cts_runtime_task_hard_cancel",
                    name=bundle.name,
                    error=str(exc),
                )
                bundle.task.cancel()
            except Exception as exc:
                if not isinstance(exc, asyncio.CancelledError):
                    logger.warning(
                        "cts_runtime_task_hard_cancel",
                        name=bundle.name,
                        error=str(exc),
                    )
                bundle.task.cancel()
        logger.info("cts_runtime_stopped")

    # -- diagnostics --------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Summary of each subscriber's task state for admin endpoints."""
        return {
            "consumer_id": self._cfg.consumer_id,
            "redis_url": self._cfg.redis_url,
            "subscribers": [
                {
                    "name": b.name,
                    "running": b.task is not None and not b.task.done(),
                    "stream": getattr(b.subscriber, "STREAM", None),
                    "group": getattr(b.subscriber, "GROUP", None),
                }
                for b in self._bundles
            ],
        }
