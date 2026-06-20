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
import logging
from dataclasses import dataclass, field
from typing import Any

from tenacity import before_sleep_log, retry, stop_after_attempt, wait_fixed

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
from backend.services.cts.event_bucketizer import (
    BucketizerRateConfig,
    CtsEventBucketizer,
    CtsWindowTrigger,
)
from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber
from backend.services.cts.identity_rewriter import IdentityRewriter
from backend.services.cts.location_repository import SqlAlchemyLocationRepository
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.ph_continuation_subscriber import PHContinuationSubscriber
from backend.services.cts.room_transition_subscriber import RoomTransitionSubscriber
from backend.services.cts.scene_sample_subscriber import SceneSampleSubscriber
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.source_authority import SourceAuthority
from backend.services.cts.stream_consumer import StreamConsumer
from backend.services.cts.subscriber import DementiaSignalSubscriber
from backend.services.cts.tracking_event_subscriber import TrackingEventSubscriber
from backend.services.cts.tracking_response_subscriber import TrackingResponseSubscriber
from backend.services.cts.world_observation_subscriber import WorldObservationSubscriber
from backend.services.cts.world_snapshot_publisher import WorldSnapshotPublisher
from backend.services.occupancy.read_model import OccupancyReadModel

logger = get_logger(__name__)


@dataclass
class CTSRuntimeConfig:
    """Runtime wiring for CTSRuntime.

    One instance per CC backend process.
    """

    redis_url: str
    consumer_id: str
    cts_lock_s: float = 60.0
    bucketizer_rate: BucketizerRateConfig = field(default_factory=BucketizerRateConfig)


@dataclass
class _SubscriberBundle:
    """Handle to one subscriber's state (subscriber + its background task)."""

    name: str
    subscriber: StreamConsumer[Any]
    task: asyncio.Task[None] | None = None


_INFERRED_DWELL_TICK_INTERVAL_S: float = 60.0


class CTSRuntime:
    """Owns the CTS subscribers and shared CTS services.

    WTR4: M4 subscribers (WorldObservation, RoomTransition,
    PHContinuation) are owned here and started/stopped with the runtime.
    Periodic inferred-dwell tick evaluates camera-blind bathroom timeouts.
    """

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
        recamera_subscriber: object | None = None,
        person_location_service: object | None = None,
        occupancy_read_model: OccupancyReadModel | None = None,
        orchestrator_client: object | None = None,
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
        # camera→room_id map: the WorldObservationSubscriber resolves room
        # membership from this directly (no name→int coercion).
        camera_id_map: dict[str, int] = {}
        if db_factory is not None:
            camera_id_map = _load_camera_room_id_map(db_factory)

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
            rate_config=config.bucketizer_rate,
        )

        self.snapshot_publisher = WorldSnapshotPublisher(
            ws_manager=ws_manager,
            person_location_service=person_location_service,
        )

        # WTR4: M4 subscribers owned and constructed by CTSRuntime. They are
        # built here (not in main.py) so the runtime can wire the camera→room
        # id map and occupancy read-model that the world tracker needs.
        self._person_location_service = person_location_service
        self.occupancy_read_model = occupancy_read_model
        self._world_observation_subscriber: WorldObservationSubscriber | None = None
        self._room_transition_subscriber: RoomTransitionSubscriber | None = None
        self._ph_continuation_subscriber: PHContinuationSubscriber | None = None
        if person_location_service is not None:
            self._world_observation_subscriber = WorldObservationSubscriber(
                redis_url=config.redis_url,
                location_service=person_location_service,  # type: ignore[arg-type]
                camera_room_id_map=camera_id_map,
                camera_room_name_map=camera_map,
                occupancy=occupancy_read_model,
                db_factory=db_factory,
            )
            self._room_transition_subscriber = RoomTransitionSubscriber(
                redis_url=config.redis_url,
                location_service=person_location_service,  # type: ignore[arg-type]
            )
            self._ph_continuation_subscriber = PHContinuationSubscriber(
                redis_url=config.redis_url,
                location_service=person_location_service,  # type: ignore[arg-type]
            )

        self.tracking_event_subscriber = TrackingEventSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
            writer=self.location_writer,
            ws_manager=ws_manager,
            pipeline=pipeline,
            bucketizer=self.bucketizer,
            minio_client=minio_client,
            snapshot_publisher=self.snapshot_publisher,
        )
        self.identity_revision_subscriber = IdentityRevisionSubscriber(
            redis_url=config.redis_url,
            consumer_id=config.consumer_id,
            rewriter=self.identity_rewriter,
            pipeline=pipeline,
            ws_manager=ws_manager,
            orchestrator_client=orchestrator_client,
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

        # Recamera observation subscriber (in-process queue, not Redis).
        self._recamera_subscriber = recamera_subscriber
        self._inferred_dwell_task: asyncio.Task[None] | None = None

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

        Each subscriber is wrapped with tenacity retry: 5 attempts, 60 s
        between attempts, then logged and abandoned if still failing.
        """

        async def _run_with_retry(bundle: _SubscriberBundle) -> None:
            @retry(
                stop=stop_after_attempt(5),
                wait=wait_fixed(60),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            )
            async def _start() -> None:
                await bundle.subscriber.start()

            try:
                await _start()
            except Exception:  # noqa: BLE001
                logger.error("cts_subscriber_retries_exhausted", name=bundle.name)

        for bundle in self._bundles:
            if bundle.task is not None and not bundle.task.done():
                continue
            task = asyncio.create_task(
                _run_with_retry(bundle),
                name=f"cts-runtime-{bundle.name}",
            )
            bundle.task = task
        await self.snapshot_publisher.start()
        # Start recamera subscriber if provided.
        if self._recamera_subscriber is not None:
            await self._recamera_subscriber.start()  # type: ignore[union-attr]
        # WTR4: start M4 subscribers.
        for m4_sub in [
            self._world_observation_subscriber,
            self._room_transition_subscriber,
            self._ph_continuation_subscriber,
        ]:
            if m4_sub is not None:
                task = asyncio.create_task(
                    _run_with_retry(
                        _SubscriberBundle(name="m4", subscriber=m4_sub)  # type: ignore[arg-type]
                    ),
                    name=f"cts-runtime-m4-{type(m4_sub).__name__}",
                )
        # Start inferred-dwell timeout evaluator if PersonLocationService is wired.
        if self._person_location_service is not None and (
            self._inferred_dwell_task is None or self._inferred_dwell_task.done()
        ):
            self._inferred_dwell_task = asyncio.create_task(
                self._run_inferred_dwell_ticker(),
                name="cts-runtime-inferred-dwell-tick",
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
        await self.snapshot_publisher.stop()
        # Stop recamera subscriber.
        if self._recamera_subscriber is not None:
            await self._recamera_subscriber.stop()  # type: ignore[union-attr]
        # WTR4: stop M4 subscribers.
        for m4_sub in [
            self._world_observation_subscriber,
            self._room_transition_subscriber,
            self._ph_continuation_subscriber,
        ]:
            if m4_sub is not None:
                try:
                    await m4_sub.stop()  # type: ignore[union-attr]
                except Exception:
                    logger.exception("m4_subscriber_stop_error", name=type(m4_sub).__name__)
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
            except Exception as exc:  # noqa: BLE001
                if not isinstance(exc, asyncio.CancelledError):
                    logger.warning(
                        "cts_runtime_task_hard_cancel",
                        name=bundle.name,
                        error=str(exc),
                    )
                bundle.task.cancel()
        # Stop inferred-dwell tick task.
        if self._inferred_dwell_task is not None and not self._inferred_dwell_task.done():
            self._inferred_dwell_task.cancel()
            try:  # noqa: SIM105 -- contextlib.suppress cannot suppress async exceptions
                await self._inferred_dwell_task
            except asyncio.CancelledError, Exception:  # noqa: BLE001
                pass

        logger.info("cts_runtime_stopped")

    async def _run_inferred_dwell_ticker(self) -> None:
        """Periodically evaluate inferred-dwell timeouts and emit signals."""
        from datetime import UTC
        from datetime import datetime as dt

        while True:
            await asyncio.sleep(_INFERRED_DWELL_TICK_INTERVAL_S)
            try:
                now = dt.now(UTC)
                svc = self._person_location_service
                if svc is None:
                    continue
                signals = await svc.tick(now)  # type: ignore[union-attr]
                for sig in signals:
                    await self.signal_store.upsert(sig)
                    logger.info(
                        "inferred_dwell_signal_persisted",
                        person_id=sig.get("person_id"),
                        signal_type=sig.get("signal_type"),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("inferred_dwell_tick_error")

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


def _load_camera_room_id_map(db_factory: DBSessionFactory) -> dict[str, int]:
    """Load camera_id → room_id mapping for enabled cameras.

    A camera contributes room membership when it has *either* a non-null
    ``room_id`` (preferred) or a ``room_name`` that resolves to a row in the
    ``rooms`` table (fallback). This matters because cameras are commonly
    configured with only a ``room_name`` and a null ``room_id`` -- without the
    fallback the map would be empty and every detection would be skipped (the
    exact break this work fixes). Cameras that resolve to no room are omitted;
    their detections are skipped with a logged warning, not silently dropped.
    """
    from backend.models.room import Room

    db = db_factory()
    try:
        rooms_by_name = {r.name: r.id for r in db.query(Room).all()}
        cameras = db.query(CtsCamera).filter(CtsCamera.enabled.is_(True)).all()
        result: dict[str, int] = {}
        for cam in cameras:
            if cam.room_id is not None:
                result[cam.id] = cam.room_id
            elif cam.room_name and cam.room_name in rooms_by_name:
                result[cam.id] = rooms_by_name[cam.room_name]
        return result
    except Exception:
        logger.exception("cts_camera_room_id_map_load_error")
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
        raise
    finally:
        db.close()
