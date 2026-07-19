"""Bootstrap phase: CTS gateway clients + runtime (gated by ``cts.enabled``).

Moved verbatim from ``backend/main.py``'s lifespan (M20): the orchestrator
and ingress-admin clients, PH enrichment/keyframe-read/identity-correction
/ReID-review services, the gait trend service, ``PersonLocationService``,
``CTSRuntime`` and its subscribers, the drift-detection poll job, and (via
``bootstrap.presence.wire_presence``, called from inside the enabled
branch at the exact point the original source calls it) ``PresenceService``.
``wire_cts_disabled`` is the ``else`` side of the same ``if`` in the
original source.

**Known pre-existing gap, not fixed here** (see
``backend/tests/test_bootstrap_wiring.py`` for the empirical confirmation):
``wire_cts_disabled`` does not set ``ha_state_cache``, ``presence``, or
``scene_sample_subscriber`` to ``None`` the way it mirrors every other
CTS-gated attribute -- those three simply do not exist on ``app.state``
when CTS is disabled. Fixing that is a behavior change and out of scope for
this refactor; it is filed as a follow-up in the M11 overview.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from backend.core.config import Settings
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.steps.base import ServiceContainer

if TYPE_CHECKING:
    from backend.services.cts.runtime import CTSRuntime
    from backend.services.guided_task.camera_selection import SensorRoomCameraTopology

logger = get_logger(__name__)


async def wire_cts(
    app: FastAPI,
    settings: Settings,
    container: ServiceContainer,
    guided_camera_topology: SensorRoomCameraTopology,
) -> CTSRuntime:
    from backend.integrations.ingress_admin_client import IngressAdminClient
    from backend.integrations.tracking_orchestrator_client import OrchestratorClient
    from backend.services.cts.event_bucketizer import BucketizerRateConfig
    from backend.services.cts.ph_enrichment import PHEnrichmentService
    from backend.services.cts.runtime import CTSRuntime, CTSRuntimeConfig
    from backend.services.person_location.repositories import (
        SqlAlchemyObservationRepository,
        SqlAlchemySegmentRepository,
    )
    from backend.services.person_location.service import PersonLocationService

    ws_manager = app.state.ws_manager
    pipeline_executor = app.state.pipeline_executor
    minio_client = app.state.minio_client
    scene_analysis_client = app.state.scene_analysis_client
    semantic_memory_client = app.state.semantic_memory_client
    occupancy_read_model = app.state.occupancy_read_model
    companion_surface_service = app.state.companion_surface_service
    zone_service = app.state.zone_service
    guided_task_service = app.state.guided_task_service
    signals_service = app.state.signals
    scheduler = app.state.scheduler
    shared_authority = app.state.source_authority

    app.state.ingress_admin_client = IngressAdminClient()
    app.state.orchestrator_client = OrchestratorClient()
    app.state.ph_enrichment_service = PHEnrichmentService(app.state.orchestrator_client)

    from backend.services.cts.keyframe_read_service import KeyframeReadService

    app.state.keyframe_read_service = KeyframeReadService(app.state.orchestrator_client)

    from backend.services.cts.identity_correction_service import (
        IdentityCorrectionService,
    )

    app.state.identity_correction_service = IdentityCorrectionService(app.state.orchestrator_client)

    from backend.services.cts.reid_review_service import ReIDReviewService

    app.state.reid_review_service = ReIDReviewService(app.state.orchestrator_client)

    from backend.services.gait_trend_service import GaitTrendService

    gait_trend_service = GaitTrendService(app.state.orchestrator_client)
    app.state.gait_trend_service = gait_trend_service

    redis_url = settings.as_str("redis.url", allow_empty=False)
    consumer_id = settings.as_str("cts.consumer_id", allow_empty=False)

    # PersonLocationService with session-aware repos.
    # Each repo method opens a short-lived session via the factory,
    # committing and closing after each operation so that TimescaleDB
    # chunk-creation locks are never held across idle periods.
    def _make_pls() -> PersonLocationService:
        return PersonLocationService(
            obs_repo=SqlAlchemyObservationRepository(get_session),
            seg_repo=SqlAlchemySegmentRepository(get_session),
        )

    person_location_service = _make_pls()
    app.state.person_location_service = person_location_service
    container.person_location = person_location_service
    companion_surface_service.set_person_location_service(person_location_service)
    zone_service.set_person_location_service(person_location_service)
    guided_task_service.set_person_location_service(person_location_service)
    app.state.activity_timeline_service.set_person_location_service(person_location_service)
    app.state.daily_report_service.set_person_location_service(person_location_service)

    # M4 subscribers (world-observation, room-transition, ph-continuation)
    # are constructed and owned by CTSRuntime, which wires the camera→room
    # id map and occupancy read-model the world tracker needs.
    cts_settings = settings.as_dict("cts")
    cts_runtime = CTSRuntime(
        config=CTSRuntimeConfig(
            redis_url=redis_url,
            consumer_id=consumer_id,
            cts_lock_s=settings.as_float("cts.lock_seconds"),
            revision_horizon_s=settings.as_float("cts.revision_horizon_s"),
            bucketizer_rate=BucketizerRateConfig.model_validate(
                {
                    "image_rate_per_second": cts_settings.get("image_rate_per_second", 0.5),
                    "image_rate_burst": cts_settings.get("image_rate_burst", 2.0),
                    "image_rate_overrides": cts_settings.get("image_rate_overrides", {}),
                }
            ),
        ),
        db_factory=get_session,
        ws_manager=ws_manager,
        pipeline=pipeline_executor,
        minio_client=minio_client,
        scene_analysis_client=scene_analysis_client,
        semantic_memory_client=semantic_memory_client,
        authority=shared_authority,
        person_location_service=person_location_service,
        occupancy_read_model=occupancy_read_model,
        orchestrator_client=getattr(app.state, "orchestrator_client", None),
    )
    app.state.cts_runtime = cts_runtime
    # Give the pipeline executor access to the CTS frame buffer so the
    # canonical media poll step and its CTS alias can return recent frames.
    # The bucketizer is built after the executor, so inject it here.
    pipeline_executor.bucketizer = cts_runtime.bucketizer
    guided_task_service.set_bucketizer(cts_runtime.bucketizer)

    from backend.services.guided_task import GuidedTaskSafetyWatch

    guided_task_service.set_safety_watch(
        GuidedTaskSafetyWatch(
            db_factory=get_session,
            person_location_service=person_location_service,
            zone_service=zone_service,
            bucketizer=cts_runtime.bucketizer,
            camera_topology=guided_camera_topology,
            identity_resolver=lambda person_id: {person_id},
            scene_analysis_client=scene_analysis_client,
            signals_service=signals_service,
            minio_client=minio_client,
            settings=settings,
        )
    )
    # Expose individual subscribers for tests / diagnostics.
    app.state.dementia_signal_subscriber = cts_runtime.dementia_signal_subscriber
    app.state.tracking_event_subscriber = cts_runtime.tracking_event_subscriber
    app.state.identity_revision_subscriber = cts_runtime.identity_revision_subscriber
    app.state.scene_sample_subscriber = cts_runtime.scene_sample_subscriber
    await cts_runtime.start()

    # -- PresenceService (Block 2: HaStateCache + HA providers) --------
    from backend.bootstrap.presence import wire_presence

    await wire_presence(app, settings, container)

    # Now that the runtime exists, surface it to the MCP tool set.
    from backend.mcp.server import _svc as _mcp_svc

    _mcp_svc.cts_runtime = cts_runtime
    _mcp_svc.person_location_service = person_location_service
    _mcp_svc.gait_trend_service = gait_trend_service
    _mcp_svc.keyframe_read_service = app.state.keyframe_read_service
    _mcp_svc.identity_correction_service = app.state.identity_correction_service
    logger.info("cts_runtime_started")

    # -- Drift detection poll (M11) -------------------------------------
    from backend.services.cts.drift_poll import poll_camera_drift

    drift_poll_interval_s = int(settings.get("cts.drift_poll_interval_s") or 3600)
    _orchestrator_client = app.state.orchestrator_client
    scheduler.add_job(
        partial(
            poll_camera_drift,
            db_factory=get_session,
            orchestrator=_orchestrator_client,
        ),
        trigger=IntervalTrigger(seconds=drift_poll_interval_s),
        id="cts_drift_poll",
        name="CTS camera drift detection poll",
        replace_existing=True,
    )
    logger.info("cts_drift_poll_scheduled", interval_s=drift_poll_interval_s)

    return cts_runtime


def wire_cts_disabled(app: FastAPI) -> None:
    app.state.ingress_admin_client = None
    app.state.orchestrator_client = None
    app.state.ph_enrichment_service = None
    app.state.keyframe_read_service = None
    app.state.identity_correction_service = None
    app.state.reid_review_service = None
    app.state.cts_runtime = None
    app.state.dementia_signal_subscriber = None
    app.state.tracking_event_subscriber = None
    app.state.identity_revision_subscriber = None
    app.state.person_location_service = None
    app.state.gait_trend_service = None
