"""Person location tracking service.

Fuses camera-based person identification with Home Assistant presence sensors
to maintain a real-time model of where each household member is located.

Camera topology
---------------
When a ``Sensor.config_json`` contains a ``movement_map`` key, the service
maps raw person-ID directions ("left-to-right" etc.) to semantic room
transitions ("entering", "exiting" …) via
:func:`~backend.services.camera_topology.infer_room_transition`.  The
resulting :class:`~backend.services.camera_topology.RoomTransition` objects
are:

1. Returned to the caller in :class:`CameraEventResult` for use by downstream
   pipeline steps (e.g. to populate ``pipeline_data["room_transitions"]``).

M38: every confirmed camera detection also writes through
:class:`~backend.services.person_location.face_sighting_ingest.FaceSightingIngest`
into ``PersonLocationService`` (the unified SSOT).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.homeassistant import HomeAssistantClient
from backend.integrations.person_id_client import PersonIDClient
from backend.models.person import (
    HouseholdMember,
    PersonActivity,
)
from backend.models.sensor import Sensor
from backend.services.camera_topology import RoomTransition, infer_room_transition
from backend.services.person_location.face_sighting_ingest import FaceSightingIngest
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import is_unknown_bucket

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class PersonDetection:
    """Lightweight representation of a single confirmed person detection.

    Attributes:
        person_id: Identifier returned by the person-ID service.
        name: Display name of the person.
        confidence: Face-match confidence score in [0, 1].
        bbox: Bounding box ``[x1, y1, x2, y2]`` in pixel coordinates.
        direction: Raw direction string from the person-ID service, or None.
        frame_index: Index into the ``media_paths`` list passed to
            :meth:`PersonTrackingService.process_camera_event`, or None.
        recognition_state: Three-valued state ("recognized" / "candidate" /
            "unrecognized").  Steps can use this to gate behaviour on face
            quality without a second network call.
        similarity: Raw cosine similarity to the best gallery centroid.
        yaw_deg: Head pose yaw in degrees (primary frontality axis).
    """

    person_id: str
    name: str
    confidence: float
    bbox: list[float]
    direction: str | None = None
    frame_index: int | None = None
    # Rich face evidence forwarded from person-identification-service.
    recognition_state: str = "recognized"
    similarity: float = 0.0
    yaw_deg: float = 0.0

    def dict(self) -> dict:
        return {
            "person_id": self.person_id,
            "name": self.name,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "direction": self.direction,
            "frame_index": self.frame_index,
            # Rich face evidence exposed to pipeline-data expression resolution
            # so steps can reference e.g. {{person_detections.0.recognition_state}}.
            "recognition_state": self.recognition_state,
            "similarity": self.similarity,
            "yaw_deg": self.yaw_deg,
        }


@dataclass(frozen=True)
class CameraFrameContext:
    """Per-frame metadata for image source routing and presence recording."""

    sensor_id: str
    room_name: str
    media_path: str
    sensor_config: dict | None = None


@dataclass
class CameraEventResult:
    """Bundled output of :meth:`PersonTrackingService.process_camera_event`.

    Attributes:
        detections: De-duplicated (highest-confidence-per-person) list of
            confirmed detections across all frames.
        room_transitions: Topology-inferred semantic transitions, one entry
            per person whose direction could be mapped via the sensor's
            ``movement_map``.  Empty list when no topology is configured.
    """

    detections: list[PersonDetection]
    room_transitions: list[RoomTransition]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PersonTrackingService:
    """Fuses camera person-ID results with HA sensor data to track person locations."""

    def __init__(
        self,
        db_session_factory,
        person_id_client: PersonIDClient,
        ha_client: HomeAssistantClient,
        face_sighting_ingest: FaceSightingIngest | None = None,
        person_location_service: PersonLocationService | None = None,
    ) -> None:
        self._db_factory = db_session_factory
        self._person_id = person_id_client
        self._ha = ha_client
        self._face_sighting_ingest = face_sighting_ingest
        self._location = person_location_service
        self._stale_minutes: int = settings.as_int("person_tracking.location_stale_minutes")
        self._ha_propagation: bool = settings.as_bool("person_tracking.ha_propagation")
        self._min_confidence: float = settings.as_float("person_id.min_confidence")

    # ------------------------------------------------------------------
    # Primary camera-event processing
    # ------------------------------------------------------------------

    async def process_camera_event(
        self,
        sensor_id: str,
        media_paths: list[str],
        room_name: str,
        include_annotated_image: bool = False,
        save_guest_images: bool = False,
        sensor_config: dict | None = None,
        *,
        frame_contexts: list[CameraFrameContext] | None = None,
    ) -> CameraEventResult:
        """Process a camera event through the person-id service.

        Steps:

        1. Download images from *media_paths* (presigned MinIO URLs or local
           paths) and encode them as base64.
        2. Send to the person-id service for identification + optional motion
           detection.
        3. De-duplicate detections across frames (keep highest confidence per
           person).
        4. Infer semantic room transitions via the sensor's topology map when
           ``sensor_config`` contains a ``movement_map``.
        5. Write into the SSOT via FaceSightingIngest.

        Args:
            sensor_id: ID of the triggering camera sensor.
            media_paths: Ordered list of presigned image URLs (or local paths).
            room_name: Name of the room the sensor is assigned to.
            include_annotated_image: Request annotated frames from the person-id
                service (bounding boxes + name labels).
            save_guest_images: Instruct the person-id service to archive frames
                that contain unidentified guests.
            sensor_config: Contents of ``Sensor.config_json`` for the
                triggering sensor, used to infer room transitions.  Pass
                ``None`` to skip topology inference.

        Returns:
            A :class:`CameraEventResult` with ``detections`` and
            ``room_transitions`` (empty list when no topology is configured).
        """
        if not self._person_id.enabled:
            return CameraEventResult(detections=[], room_transitions=[])

        images_b64 = await self._load_images_as_base64(media_paths)
        if not images_b64:
            return CameraEventResult(detections=[], room_transitions=[])

        include_motion = settings.as_bool("person_id.include_motion")
        batch_result = await self._person_id.identify_batch(
            images_b64,
            include_motion=include_motion,
            include_annotated_image=include_annotated_image,
            save_guest_images=save_guest_images,
        )
        if not batch_result:
            return CameraEventResult(detections=[], room_transitions=[])

        # Build direction lookup from motion results (person_id → direction).
        direction_map: dict[str, str] = {m.person_id: m.direction for m in batch_result.motion}

        # De-duplicate: keep the highest-confidence detection per person across
        # all frames, preserving the frame_index for bbox-to-media correlation.
        best: dict[str, PersonDetection] = {}
        for frame_idx, frame_faces in enumerate(batch_result.frames):
            for face in frame_faces:
                if face.confidence < self._min_confidence:
                    continue
                existing = best.get(face.person_id)
                if not existing or face.confidence > existing.confidence:
                    best[face.person_id] = PersonDetection(
                        person_id=face.person_id,
                        name=face.name,
                        confidence=face.confidence,
                        bbox=face.bbox,
                        direction=direction_map.get(face.person_id),
                        frame_index=frame_idx,
                        # Rich face evidence forwarded from person-id service.
                        recognition_state=face.recognition_state,
                        similarity=face.similarity,
                        yaw_deg=face.yaw_deg,
                    )

        detections = list(best.values())

        # Build default frame contexts when not provided.
        if frame_contexts is None:
            frame_contexts = [
                CameraFrameContext(
                    sensor_id=sensor_id,
                    room_name=room_name,
                    media_path=mp,
                    sensor_config=sensor_config,
                )
                for mp in media_paths
            ]

        def _ctx_for_det(det_idx: int | None) -> CameraFrameContext:
            if det_idx is not None and 0 <= det_idx < len(frame_contexts):
                return frame_contexts[det_idx]
            return CameraFrameContext(
                sensor_id=sensor_id, room_name=room_name, media_path="", sensor_config=sensor_config
            )

        # Persist sightings and location state.
        transition_by_person: dict[str, RoomTransition] = {}
        db: Session = self._db_factory()
        try:
            for det in detections:
                ctx = _ctx_for_det(det.frame_index)
                det_sensor_id = ctx.sensor_id or sensor_id
                det_room_name = ctx.room_name or room_name
                det_sensor_cfg = ctx.sensor_config or sensor_config

                # Re-infer room transitions with the per-frame sensor config and room.
                det_transition = infer_room_transition(
                    person_id=det.person_id,
                    person_name=det.name,
                    sensor_id=det_sensor_id,
                    direction_raw=det.direction,
                    confidence=det.confidence,
                    sensor_config=det_sensor_cfg,
                )
                if det_transition is not None:
                    transition_by_person[det.person_id] = det_transition

                self._ensure_member_exists(db, det.person_id)

                if self._face_sighting_ingest is not None:
                    await self._face_sighting_ingest.ingest(
                        person_id=det.person_id,
                        sensor_id=det_sensor_id,
                        room_name=det_room_name,
                        confidence=det.confidence,
                        raw_similarity=det.similarity,
                    )
        finally:
            db.close()

        # Update room transitions list with re-inferred transitions.
        transitions = list(transition_by_person.values())

        return CameraEventResult(detections=detections, room_transitions=transitions)

    # ------------------------------------------------------------------
    # HA presence sensor polling
    # ------------------------------------------------------------------

    async def poll_ha_presence_sensors(self) -> None:
        """Poll HA presence sensors for rooms without cameras.

        When a presence sensor activates, correlate with recent camera sightings
        to infer which person is in that room.
        """
        db: Session = self._db_factory()
        try:
            sensors = (
                db.query(Sensor)
                .filter(
                    Sensor.sensor_type == "presence",
                    Sensor.enabled.is_(True),
                    Sensor.source == "homeassistant",
                )
                .all()
            )
            for sensor in sensors:
                await self._correlate_presence_sensor(sensor, db)
        except Exception:
            logger.exception("person_tracking_poll_error")
        finally:
            db.close()

    async def _correlate_presence_sensor(self, sensor: Sensor, db: Session) -> None:
        """Infer person identity when a binary presence sensor reads "on".

        M38 Part E: candidate discovery moves onto the SSOT
        (``PersonLocationService.recent_observations``, world_tracker +
        face_sighting, same 10-minute window the legacy ``PersonSighting``
        query used) and the already-in-room / fresh-elsewhere skip checks
        re-express against ``where_is``/``latest_observation`` -- decision
        semantics unchanged, only the data source moves (M32 discipline).
        The legacy ``_record_sighting``/``_update_location_state`` writes
        stay as the deliberate double-write bridge (Part D.2's rule); this
        method additionally writes through to the SSOT
        (``source="sensor"``), letting the arbiter's priority-40 handoff
        reproduce the "HA writes only when cameras are quiet" behavior
        ``SourceAuthority`` used to provide, now in one place.

        Candidates from the unknown bucket (W7) are skipped: they surface as
        real observation rows (audit parity) but must never gain a segment
        or correlation, or every unidentified visitor collapses onto one
        open segment.
        """
        ha_entity = sensor.ha_entity_id or f"binary_sensor.{sensor.id}_person_information"

        try:
            state_data = await self._ha.get_entity_state(ha_entity)
            state = state_data.get("state", "off") if state_data else "off"
        except Exception:  # noqa: BLE001
            return

        if state != "on":
            return

        if self._location is None:
            return

        room_name = sensor.room.name if sensor.room else "Unknown"
        room_id = sensor.room.id if sensor.room is not None else None
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=10)

        recent = await self._location.recent_observations(
            cutoff, sources=("world_tracker", "face_sighting"), limit=20
        )
        if not recent:
            return

        seen: set[str] = set()
        for obs in recent:
            person_id = obs.person_id
            if person_id in seen:
                continue
            seen.add(person_id)
            if is_unknown_bucket(person_id):
                # W7: the unknown bucket is a merged pseudo-person shared by
                # every unidentified visitor. HA correlation can't
                # meaningfully single one out, and opening a segment for it
                # would churn one open segment across all of them.
                continue

            current = await self._location.where_is(person_id)
            if current is not None and room_id is not None and current.room_id == room_id:
                continue  # already correctly placed
            if current is not None and (room_id is None or current.room_id != room_id):
                latest = await self._location.latest_observation(person_id)
                if latest is not None and (now - latest.observed_at).total_seconds() < 60:
                    continue  # fresh elsewhere, don't override

            self._ensure_member_exists(db, person_id)
            await self._location.ingest_observation(
                person_id=person_id,
                observed_at=now,
                source="sensor",
                confidence=0.6,
                room_id=room_id,
                metadata={"sensor_id": sensor.id, "room_name": room_name},
            )
            break

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _ensure_member_exists(self, db: Session, person_id: str) -> None:
        """Ensure HouseholdMember exists for guests."""
        member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
        if not member:
            is_guest = person_id == "unknown" or person_id.startswith("unknown_")
            member = HouseholdMember(
                id=person_id,
                name="Guest" if is_guest else person_id,
                is_guest=is_guest,
            )
            db.add(member)
            db.flush()

    async def record_activity(
        self,
        person_id: str,
        activity_type: str,
        room_name: str | None,
        confidence: float,
        source_event_id: int | None = None,
        metadata: dict | None = None,
    ) -> PersonActivity:
        """Record a detected activity for a person.

        Returns:
            The created :class:`~backend.models.person.PersonActivity` instance.
        """
        from backend.models.room import Room

        db: Session = self._db_factory()
        try:
            room_id: int | None = None
            if room_name:
                room = db.query(Room).filter(Room.name == room_name).first()
                room_id = room.id if room else None

            activity = PersonActivity(
                person_id=person_id,
                activity_type=activity_type,
                room_id=room_id,
                room_name=room_name,
                confidence=confidence,
                source_event_id=source_event_id,
                metadata_json=metadata,
            )
            db.add(activity)
            db.commit()
            logger.info(
                "activity_recorded",
                person_id=person_id,
                activity_type=activity_type,
                room=room_name,
            )
            return activity
        except Exception:
            db.rollback()
            logger.exception("record_activity_error", person_id=person_id)
            raise
        finally:
            db.close()

    async def get_recent_activities(
        self,
        person_id: str,
        activity_type: str | None = None,
        minutes: float = 60,
    ) -> list[dict]:
        """Return recent activities for a person, optionally filtered by type."""
        db: Session = self._db_factory()
        try:
            cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
            query = db.query(PersonActivity).filter(
                PersonActivity.person_id == person_id,
                PersonActivity.detected_at >= cutoff,
            )
            if activity_type:
                query = query.filter(PersonActivity.activity_type == activity_type)

            activities = query.order_by(desc(PersonActivity.detected_at)).limit(50).all()
            return [
                {
                    "id": a.id,
                    "person_id": a.person_id,
                    "activity_type": a.activity_type,
                    "room_name": a.room_name,
                    "detected_at": a.detected_at.isoformat() if a.detected_at else None,
                    "confidence": a.confidence,
                }
                for a in activities
            ]
        finally:
            db.close()

    async def query_activities_in_window(
        self,
        person_id: str | None,
        activity_type: str,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        within_minutes: float | None = None,
        min_confidence: float = 0.0,
        room_name: str | None = None,
    ) -> list[dict]:
        """Query activities within a time window.

        Supports two modes:

        - **Relative**: pass *within_minutes* to query from ``now - minutes``
          to now.
        - **Absolute**: pass *window_start* and/or *window_end* as UTC
          datetimes.

        If both *within_minutes* and explicit boundaries are provided,
        *within_minutes* takes precedence.
        """
        now = datetime.now(UTC)

        if within_minutes is not None:
            effective_start: datetime | None = now - timedelta(minutes=within_minutes)
            effective_end: datetime | None = now
        else:
            effective_start = window_start
            effective_end = window_end or now

        db: Session = self._db_factory()
        try:
            query = db.query(PersonActivity).filter(
                PersonActivity.activity_type == activity_type,
                PersonActivity.confidence >= min_confidence,
            )
            if person_id:
                query = query.filter(PersonActivity.person_id == person_id)
            if room_name:
                query = query.filter(PersonActivity.room_name == room_name)
            if effective_start:
                query = query.filter(PersonActivity.detected_at >= effective_start)
            if effective_end:
                query = query.filter(PersonActivity.detected_at <= effective_end)

            activities = query.order_by(desc(PersonActivity.detected_at)).limit(50).all()
            return [
                {
                    "id": a.id,
                    "person_id": a.person_id,
                    "activity_type": a.activity_type,
                    "room_name": a.room_name,
                    "detected_at": a.detected_at.isoformat() if a.detected_at else None,
                    "confidence": a.confidence,
                }
                for a in activities
            ]
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_images_as_base64(media_paths: list[str]) -> list[str]:
        """Convert media paths (presigned URLs or local files) to base64 strings."""
        images: list[str] = []
        for path in media_paths:
            try:
                if path.startswith(("http://", "https://")):
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.get(path)
                        resp.raise_for_status()
                        images.append(base64.b64encode(resp.content).decode("utf-8"))
                else:
                    with open(path, "rb") as f:
                        images.append(base64.b64encode(f.read()).decode("utf-8"))
            except Exception:  # noqa: BLE001
                logger.warning("failed_to_load_image", path=path[:100])
        return images
