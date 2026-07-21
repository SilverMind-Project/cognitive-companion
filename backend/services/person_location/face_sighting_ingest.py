"""FaceSightingIngest: writes reCamera-identified detections to the SSOT.

M38 Part D (decision W7): reCamera identification stays rule-driven --
``PersonTrackingService`` remains the identification engine and cost
throttle -- but every confirmed detection now also flows through this one
adapter into ``PersonLocationService``, instead of being location-blind to
the SSOT (X11). ``PersonTrackingService.process_camera_event`` calls
:meth:`FaceSightingIngest.ingest` for each deduplicated detection
    *alongside* its existing legacy-table writes, so a later milestone can
    delete the legacy half once this soaks.

This adapter never writes floor points: reCamera detections carry no floor
coordinates, so inventing one would repeat the exact (0, 0)-poisoning
mistake ``WorldObservationSubscriber``'s calibration gate exists to avoid.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.models.sensor import Sensor
from backend.services.cts.identity_assertion_publisher import IdentityAssertionPublisher
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import is_unknown_bucket

if TYPE_CHECKING:
    from backend.services.occupancy.read_model import OccupancyReadModel

logger = get_logger(__name__)


class FaceSightingIngest:
    """Writes one confirmed reCamera detection to ``PersonLocationService``.

    The unknown bucket gets an observation row and a provisioned guest
    member (audit parity with the legacy tables), but no segment and no
    identity assertion: giving it presence segments would churn one open
    segment across every unidentified visitor in the house, and asserting
    it to the orchestrator would poison its Bayesian identity resolver with
    a non-identity. Identified persons and named guests also record room
    presence into ``OccupancyReadModel`` under stable hypothesis key
    ``face_{person_id}`` (the unknown bucket is excluded from occupancy for
    the same absence of stable hypothesis ID across frames).
    """

    def __init__(
        self,
        db_factory: Callable[[], Session],
        location_service: PersonLocationService,
        assertion_publisher: IdentityAssertionPublisher | None,
        *,
        publish_assertions: bool,
        occupancy_read_model: OccupancyReadModel | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._location = location_service
        self._assertion_publisher = assertion_publisher
        self._publish_assertions = publish_assertions
        self._occupancy_read_model = occupancy_read_model

    async def ingest(
        self,
        *,
        person_id: str,
        sensor_id: str,
        room_name: str,
        confidence: float,
        raw_similarity: float = 0.0,
        calibrated_confidence: float | None = None,
        calibration_status: str = "uncalibrated",
        yaw_deg: float | None = None,
        transition: Any | None = None,
    ) -> None:
        """Ingest one confirmed detection. Never raises: logs and returns on failure.

        Uses ingest-time ``datetime.now(UTC)`` as ``observed_at``:
        ``TriggerContext`` carries no capture timestamp and
        ``EventAggregator`` buffers only media paths, so this is an
        enumerated approximation (up to ~90s of capture-to-ingest lag),
        made safe by the SSOT's out-of-order guard (a lagged write can no
        longer rewrite fresher evidence).
        """
        try:
            room_id = self._resolve_room_id(sensor_id, room_name)
            is_unknown = is_unknown_bucket(person_id)
            self._ensure_member(person_id, is_guest=is_unknown)

            now = datetime.now(UTC)
            obs_metadata: dict[str, Any] = {"camera_id": sensor_id, "room_name": room_name}
            if transition is not None:
                obs_metadata["from_room"] = transition.from_room_name
                obs_metadata["direction"] = transition.semantic

            await self._location.ingest_observation(
                person_id=person_id,
                observed_at=now,
                source="face_sighting",
                confidence=confidence,
                metadata=obs_metadata,
                room_id=room_id,
                # The unknown bucket is a merged pseudo-person: give it an
                # observation row for audit parity, but never a segment (it
                # would churn one open segment across every unidentified
                # visitor in the house).
                skip_segment=is_unknown,
            )

            if not is_unknown and room_id is not None and self._occupancy_read_model is not None:
                from backend.services.occupancy.read_model import FACE_SIGHTING_SOURCE

                self._occupancy_read_model.record_room_presence(
                    room_id=room_id,
                    room_name=room_name,
                    ph_id=f"face_{person_id}",
                    identity_id=person_id,
                    source=FACE_SIGHTING_SOURCE,
                    observed_at=now,
                )

            if is_unknown:
                return

            if self._publish_assertions and self._assertion_publisher is not None:
                # No floor coordinates: reCameras have no spatial calibration on
                # either side (verified 2026-07-19), so the room-name gate is the
                # only spatial match available to the orchestrator. No face-crop
                # quality value exists in the person-identification-service
                # response today; omitted so the consumer's conservative default
                # applies (identity-continuity M09).
                await self._assertion_publisher.publish(
                    person_id=person_id,
                    confidence=confidence,
                    camera_id=sensor_id,
                    captured_at=now,
                    raw_similarity=raw_similarity,
                    calibrated_confidence=calibrated_confidence,
                    calibration_status=calibration_status,
                    source="cc-face-sighting",
                    room_name=room_name,
                    yaw_deg=yaw_deg,
                )
        except Exception:
            logger.exception(
                "face_sighting_ingest_failed",
                person_id=person_id,
                sensor_id=sensor_id,
            )

    def _resolve_room_id(self, sensor_id: str, room_name: str) -> int | None:
        """Sensor.room first; Room.name lookup only when the sensor has no binding."""
        db = self._db_factory()
        try:
            sensor = db.query(Sensor).filter(Sensor.id == sensor_id).first()
            if sensor is not None and sensor.room_id is not None:
                return sensor.room_id

            room = db.query(Room).filter(Room.name == room_name).first()
            if room is not None:
                return room.id

            logger.warning(
                "recamera_location_ingest_room_unresolved",
                sensor_id=sensor_id,
                room_name=room_name,
            )
            return None
        finally:
            db.close()

    def _ensure_member(self, person_id: str, *, is_guest: bool) -> None:
        """Auto-provision a guest HouseholdMember row so the SSOT FK cannot fail (X16).

        Mirrors ``PersonTrackingService._record_sighting``'s legacy
        provisioning: enrolled residents already have a row (created via
        household onboarding), so this path fires in practice only for the
        unknown bucket and un-enrolled guests.
        """
        db = self._db_factory()
        try:
            member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
            if member is not None:
                return
            db.add(
                HouseholdMember(
                    id=person_id,
                    name="Guest" if is_guest else person_id,
                    is_guest=is_guest,
                )
            )
            db.commit()
        finally:
            db.close()
