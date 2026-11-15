"""Identity readiness: one place that says which link of the identity chain is broken.

One service method powers the BFF route (``GET /api/v1/identity/readiness``) and the
``get_identity_readiness`` MCP tool. It reads, never writes: roster health and calibration state
from person-identification-service, the identity policies and gallery counts from the tracking
orchestrator, live frame age from rtsp-ingress, and the floor plan, rooms, cameras, and overlap
groups from CC's own tables. The per-step rules are in ``identity_readiness_rules``.

A failing source marks only its own steps ``unknown``; the page exists to diagnose partial
outages, so one stopped service never fails the whole response and never reads as healthy.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError
from backend.integrations.ingress_admin_client import IngressAdminClient
from backend.integrations.person_id_client import PersonIDClient, PersonIDUpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.models.cts_camera import CtsCamera
from backend.models.cts_dashboard import CtsCameraOverlapGroup
from backend.models.household_settings import HouseholdSettings
from backend.models.room import Room
from backend.schemas.identity_readiness import CTSIdentityReadiness, IdentityReadinessEnvelope
from backend.services.identity_readiness_rules import (
    ARTIFACT_READY,
    CameraConfig,
    HouseholdFloorFrame,
    IngestHealth,
    SourceFailure,
    artifact_step,
    body_gallery_step,
    capture_step,
    face_policy_step,
    floor_frame_step,
    ingest_step,
    labeling_step,
    roster_step,
    templates_step,
)
from backend.services.identity_roster import RosterHealthService

logger = get_logger(__name__)


async def _attempt[T](source: str, call: Awaitable[T]) -> T | SourceFailure:
    try:
        return await call
    except (PersonIDUpstreamError, UpstreamError, ValidationError) as exc:
        logger.warning("identity_readiness_source_failed", source=source, error=type(exc).__name__)
        return SourceFailure(source)


class IdentityReadinessService:
    def __init__(
        self,
        *,
        roster: RosterHealthService,
        person_id: PersonIDClient,
        session_factory: Callable[[], Session],
        orchestrator: OrchestratorClient | None,
        ingress: IngressAdminClient | None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._roster = roster
        self._person_id = person_id
        self._session_factory = session_factory
        self._orchestrator = orchestrator
        self._ingress = ingress
        self._clock = clock

    async def get_readiness(self) -> IdentityReadinessEnvelope:
        household = self._household_floor_frame()
        roster, summary, health, members, cts, ingest = await asyncio.gather(
            _attempt("person identification", self._roster.get_roster_health()),
            _attempt("person identification", self._person_id.get_calibration_summary()),
            _attempt("person identification", self._person_id.get_calibration_health()),
            _attempt("person identification", self._person_id.list_members()),
            self._cts_readiness(),
            self._ingest_health([c.camera_id for c in household.cameras]),
        )
        artifact_ready = not isinstance(health, SourceFailure) and health.status == ARTIFACT_READY
        steps = [
            roster_step(roster),
            ingest_step(ingest),
            floor_frame_step(household, cts),
            capture_step(summary, health),
            labeling_step(summary),
            artifact_step(health, members),
            face_policy_step(cts, artifact_ready),
            templates_step(cts, health),
            body_gallery_step(cts),
        ]
        blocking = next((s.key for s in steps if s.state == "blocked" and not s.optional), None)
        return IdentityReadinessEnvelope(
            steps=steps, blocking_step=blocking, checked_at=self._clock()
        )

    async def _cts_readiness(self) -> CTSIdentityReadiness | SourceFailure:
        if self._orchestrator is None:
            return SourceFailure("the tracking orchestrator (CTS is disabled)")
        raw = await _attempt("the tracking orchestrator", self._orchestrator.identity_readiness())
        if isinstance(raw, SourceFailure):
            return raw
        try:
            return CTSIdentityReadiness.model_validate(raw)
        except ValidationError:
            logger.warning("identity_readiness_cts_contract_violation")
            return SourceFailure("the tracking orchestrator")

    async def _ingest_health(self, camera_ids: list[str]) -> IngestHealth | SourceFailure:
        ingress = self._ingress
        if ingress is None:
            return SourceFailure("camera ingest (CTS is disabled)")

        async def frame_age(camera_id: str) -> float | None:
            result = await _attempt("camera ingest", ingress.stream_health(camera_id=camera_id))
            if isinstance(result, SourceFailure):
                return None
            age = result.get("last_frame_age_s")
            return float(age) if isinstance(age, int | float) else None

        ages = await asyncio.gather(*(frame_age(cid) for cid in camera_ids))
        return IngestHealth(frame_age_s=dict(zip(camera_ids, ages, strict=True)))

    def _household_floor_frame(self) -> HouseholdFloorFrame:
        db = self._session_factory()
        try:
            plan = db.get(HouseholdSettings, 1)
            rooms = db.query(Room.floor_polygon).all()
            cameras = (
                db.query(CtsCamera.id, CtsCamera.role, CtsCamera.homography_matrix)
                .filter(CtsCamera.enabled.is_(True))
                .order_by(CtsCamera.id)
                .all()
            )
            group_count = db.query(CtsCameraOverlapGroup).count()
        finally:
            db.close()
        return HouseholdFloorFrame(
            has_floor_plan=plan is not None and bool(plan.floor_plan_key),
            has_scale=plan is not None and bool(plan.floor_meters_per_pixel),
            room_count=len(rooms),
            rooms_with_polygon=sum(1 for r in rooms if r.floor_polygon),
            cameras=tuple(
                CameraConfig(camera_id=c.id, role=c.role, has_homography=bool(c.homography_matrix))
                for c in cameras
            ),
            overlap_group_count=group_count,
        )
