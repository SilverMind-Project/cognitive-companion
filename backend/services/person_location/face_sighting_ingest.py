"""FaceSightingIngest: writes reCamera-identified detections to the SSOT.

M38 Part D (decision W7): reCamera identification stays rule-driven --
``PersonTrackingService`` remains the identification engine and cost
throttle -- but every confirmed detection now also flows through this one
adapter into ``PersonLocationService``, instead of being location-blind to
the SSOT (X11). ``PersonTrackingService.process_camera_event`` calls
:meth:`FaceSightingIngest.ingest` for each deduplicated detection
*alongside* its existing legacy-table writes: the same deliberate
double-write bridge ``LocationWriter`` provides on the CTS side, so a later
milestone can delete the legacy half once this soaks.

This adapter never writes floor points: reCamera detections carry no floor
coordinates, so inventing one would repeat the exact (0, 0)-poisoning
mistake ``WorldObservationSubscriber``'s calibration gate exists to avoid.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.models.sensor import Sensor
from backend.services.cts.identity_assertion_publisher import IdentityAssertionPublisher
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import is_unknown_bucket

logger = get_logger(__name__)


class FaceSightingIngest:
    """Writes one confirmed reCamera detection to ``PersonLocationService``.

    The unknown bucket gets an observation row and a provisioned guest
    member (audit parity with the legacy tables), but no segment and no
    identity assertion: giving it presence segments would churn one open
    segment across every unidentified visitor in the house, and asserting
    it to the orchestrator would poison its Bayesian identity resolver with
    a non-identity.
    """

    def __init__(
        self,
        db_factory: Callable[[], Session],
        location_service: PersonLocationService,
        assertion_publisher: IdentityAssertionPublisher | None,
        *,
        publish_assertions: bool,
    ) -> None:
        self._db_factory = db_factory
        self._location = location_service
        self._assertion_publisher = assertion_publisher
        self._publish_assertions = publish_assertions

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
            await self._location.ingest_observation(
                person_id=person_id,
                observed_at=now,
                source="face_sighting",
                confidence=confidence,
                metadata={"camera_id": sensor_id, "room_name": room_name},
                room_id=room_id,
                # The unknown bucket is a merged pseudo-person: give it an
                # observation row for audit parity, but never a segment (it
                # would churn one open segment across every unidentified
                # visitor in the house).
                skip_segment=is_unknown,
            )

            if is_unknown:
                return

            if self._publish_assertions and self._assertion_publisher is not None:
                await self._assertion_publisher.publish(
                    person_id=person_id,
                    confidence=confidence,
                    camera_id=sensor_id,
                    captured_at=now,
                    raw_similarity=raw_similarity,
                    calibrated_confidence=calibrated_confidence,
                    calibration_status=calibration_status,
                    source="cc-recamera-vlm",
                )
        except Exception:
            logger.exception(
                "recamera_location_ingest_failed",
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
