"""CTSRuntime: lifecycle manager for the CTS subscribers.

A single owner so ``main.py`` lifespan does not grow three copies of the
same start/stop boilerplate. Constructing ``CTSRuntime`` does not start any
I/O; call :meth:`start` inside the lifespan and :meth:`stop` on shutdown.

If ``cts.enabled`` is ``False``, ``main.py`` never calls :meth:`start` - the
runtime object is not constructed, which keeps the feature-flag guarantee
that no CTS code executes when the flag is off.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.core.logging import get_logger
from backend.models.cts_camera import CtsCamera
from backend.services.cts._types import (
    ConnectionManager,
    DBSessionFactory,
    MinioClient,
    PipelineExecutor,
    SceneAnalysisClient,
    SemanticMemoryClient,
)
from backend.services.cts.event_bucketizer import CtsEventBucketizer, CtsWindowTrigger
from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber
from backend.services.cts.identity_rewriter import IdentityRewriter
from backend.services.cts.location_repository import SqlAlchemyLocationRepository
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.scene_sample_subscriber import SceneSampleSubscriber
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.source_authority import SourceAuthority
from backend.services.cts.stream_consumer import StreamConsumer
from backend.services.cts.subscriber import DementiaSignalSubscriber
from backend.services.cts.tracking_event_subscriber import TrackingEventSubscriber
from backend.services.cts.tracking_response_subscriber import TrackingResponseSubscriber

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
    subscriber: StreamConsumer[Any]
    task: asyncio.Task[None] | None = None


class CTSRuntime:
    """Owns the five CTS subscribers and shared CTS services."""

    def __init__(
        self,
        *,
        config: CTSRuntimeConfig,
        db_factory: DBSessionFactory,
        ws_manager: ConnectionManager | None = None,
        pipeline: PipelineExecutor | None = None,
        minio_client: MinioClient | None = None,
        scene_analysis_client: SceneAnalysisClient | None = None,
        semantic_memory_client: SemanticMemoryClient | None = None,
        camera_room_map: dict[str, str] | None = None,
        authority: SourceAuthority | None = None,
    ) -> None:
        self._cfg = config
        self._db_factory = db_factory
        self._ws_manager = ws_manager
        self._pipeline = pipeline

        if authority is None:
            authority = SourceAuthority(cts_lock_s=config.cts_lock_s)
        self.authority = authority

        def _repo_factory() -> SqlAlchemyLocationRepository:
            return SqlAlchemyLocationRepository(db_factory())

        # Build camera→room mapping from the CtsCamera table at startup.
        # Cameras rarely change location, so this is loaded once and used
        # by both LocationWriter (room_name fallback) and SceneSampleSubscriber.
        camera_map = camera_room_map if camera_room_map is not None else {}
        if not camera_map and db_factory is not None:
            camera_map = _load_camera_room_map(db_factory)

        self.location_writer = LocationWriter(
            repo_factory=_repo_factory,
            authority=self.authority,
            camera_room_map=camera_map,
        )
        self.identity_rewriter = IdentityRewriter(db_factory=db_factory, ws_manager=ws_manager)
        self.signal_store = SignalStore(db_factory=db_factory)

        # Bucketizer for cts_window triggers. Loads enabled triggers from the
        # DB at startup and caches them; call ``reload_triggers()`` to refresh.
        def _load_triggers() -> list[CtsWindowTrigger]:
            return _load_window_triggers(db_factory)

        self.bucketizer = CtsEventBucketizer(
            pipeline=pipeline,
            get_triggers=_load_triggers,
        )

        self.tracking_event_subscriber = TrackingEventSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
            writer=self.location_writer,
            ws_manager=ws_manager,
            pipeline=pipeline,
            bucketizer=self.bucketizer,
            minio_client=minio_client,
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
            db_factory=db_factory,
        )
        self.scene_sample_subscriber = SceneSampleSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
            minio_client=minio_client,
            scene_analysis_client=scene_analysis_client,
            semantic_memory_client=semantic_memory_client,
            camera_room_map=camera_map,
        )
        self.tracking_response_subscriber = TrackingResponseSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
        )

        self._bundles: list[_SubscriberBundle] = [
            _SubscriberBundle(name="tracking_events", subscriber=self.tracking_event_subscriber),
            _SubscriberBundle(
                name="identity_revisions", subscriber=self.identity_revision_subscriber
            ),
            _SubscriberBundle(name="dementia_signals", subscriber=self.dementia_signal_subscriber),
            _SubscriberBundle(name="scene_samples", subscriber=self.scene_sample_subscriber),
            _SubscriberBundle(
                name="tracking_responses", subscriber=self.tracking_response_subscriber
            ),
        ]

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Start all five CTS subscribers as background tasks.

        Idempotent: calling start twice is a no-op on already-running tasks.
        """
        def _on_done(bundle_name: str) -> Callable[[asyncio.Task[None]], None]:
            def _cb(task: asyncio.Task[None]) -> None:
                if task.cancelled():
                    return
                exc = task.exception()
                if exc is not None:
                    logger.error(
                        "cts_subscriber_task_failed",
                        name=bundle_name,
                        error=repr(exc),
                        exc_info=exc,
                    )
            return _cb

        for bundle in self._bundles:
            if bundle.task is not None and not bundle.task.done():
                continue
            task = asyncio.create_task(
                bundle.subscriber.start(),
                name=f"cts-runtime-{bundle.name}",
            )
            task.add_done_callback(_on_done(bundle.name))
            bundle.task = task
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
                    logger.exception("cts_runtime_subscriber_stop_error", name=bundle.name)

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


def _load_camera_room_map(db_factory: DBSessionFactory) -> dict[str, str]:
    """Load camera_id to room_name mapping from the CtsCamera table."""
    db = db_factory()
    try:
        cameras = db.query(CtsCamera).filter(CtsCamera.enabled.is_(True)).all()
        return {cam.id: cam.room_name or "" for cam in cameras}
    except Exception:
        logger.exception("cts_camera_room_map_load_error")
        raise
    finally:
        db.close()


def _load_window_triggers(db_factory: DBSessionFactory) -> list[CtsWindowTrigger]:
    """Load enabled CtsWindowTrigger rows and convert to in-memory config."""
    from backend.models.cts_window_trigger import (
        CtsWindowTrigger as CtsWindowTriggerModel,
    )

    db = db_factory()
    try:
        rows = db.query(CtsWindowTriggerModel).filter(CtsWindowTriggerModel.enabled.is_(True)).all()
        return [
            CtsWindowTrigger(
                id=row.id,
                name=row.name,
                window_seconds=row.window_seconds,
                min_detections=row.min_detections,
                min_identities=row.min_identities,
                cameras=row.cameras,
                rooms=row.rooms,
                cooldown_seconds=row.cooldown_seconds,
                enabled=row.enabled,
            )
            for row in rows
        ]
    except Exception:
        logger.exception("cts_window_triggers_load_error")
        return []
    finally:
        db.close()
