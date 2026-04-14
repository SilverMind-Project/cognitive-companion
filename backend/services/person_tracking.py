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

1. Stored as metadata on the :class:`~backend.models.person.PersonLocationHistory`
   row written for the transition (``direction_semantic``, ``from_room_*``).
2. Returned to the caller in :class:`CameraEventResult` for use by downstream
   pipeline steps (e.g. to populate ``pipeline_data["room_transitions"]``).
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
    PersonLocationHistory,
    PersonLocationState,
    PersonSighting,
)
from backend.models.sensor import Sensor
from backend.services.camera_topology import RoomTransition, infer_room_transition

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
    """

    person_id: str
    name: str
    confidence: float
    bbox: list[float]
    direction: str | None = None
    frame_index: int | None = None

    def dict(self) -> dict:
        return {
            "person_id": self.person_id,
            "name": self.name,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "direction": self.direction,
            "frame_index": self.frame_index,
        }


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
        ws_manager=None,
    ) -> None:
        self._db_factory = db_session_factory
        self._person_id = person_id_client
        self._ha = ha_client
        self._ws_manager = ws_manager
        self._stale_minutes: int = settings.get("person_tracking.location_stale_minutes", 30)
        self._ha_propagation: bool = settings.get("person_tracking.ha_propagation", True)
        self._min_confidence: float = settings.get("person_id.min_confidence", 0.5)

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
        5. Write :class:`~backend.models.person.PersonSighting` and update
           :class:`~backend.models.person.PersonLocationState` /
           :class:`~backend.models.person.PersonLocationHistory` for each
           detection.

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

        include_motion = settings.get("person_id.include_motion", True)
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
                    )

        detections = list(best.values())

        # Infer room transitions via camera topology map.
        transitions: list[RoomTransition] = []
        transition_by_person: dict[str, RoomTransition] = {}
        for det in detections:
            t = infer_room_transition(
                person_id=det.person_id,
                person_name=det.name,
                sensor_id=sensor_id,
                direction_raw=det.direction,
                confidence=det.confidence,
                sensor_config=sensor_config,
            )
            if t is not None:
                transitions.append(t)
                transition_by_person[det.person_id] = t

        # Persist sightings and location state.
        db: Session = self._db_factory()
        try:
            for det in detections:
                await self._record_sighting(
                    db=db,
                    person_id=det.person_id,
                    sensor_id=sensor_id,
                    room_name=room_name,
                    confidence=det.confidence,
                    direction=det.direction,
                    bbox=det.bbox,
                    source="camera",
                )
                await self._update_location_state(
                    db=db,
                    person_id=det.person_id,
                    room_name=room_name,
                    sensor_id=sensor_id,
                    confidence=det.confidence,
                    source="camera",
                    room_transition=transition_by_person.get(det.person_id),
                )
        finally:
            db.close()

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
        """Infer person identity when a binary presence sensor reads "on"."""
        ha_entity = sensor.ha_entity_id or f"binary_sensor.{sensor.id}_person_information"

        try:
            state_data = await self._ha.get_entity_state(ha_entity)
            state = state_data.get("state", "off") if state_data else "off"
        except Exception:
            return

        if state != "on":
            return

        room_name = sensor.room.name if sensor.room else "Unknown"
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=10)

        recent_sightings = (
            db.query(PersonSighting)
            .filter(
                PersonSighting.timestamp >= cutoff,
                PersonSighting.source == "camera",
            )
            .order_by(desc(PersonSighting.timestamp))
            .limit(20)
            .all()
        )
        if not recent_sightings:
            return

        for sighting in recent_sightings:
            loc_state = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == sighting.person_id)
                .first()
            )
            if loc_state and loc_state.current_room_name == room_name:
                continue
            if (
                loc_state
                and loc_state.current_room_name != room_name
                and loc_state.last_seen_at
                and (now - loc_state.last_seen_at).total_seconds() < 60
            ):
                continue

            await self._record_sighting(
                db=db,
                person_id=sighting.person_id,
                sensor_id=sensor.id,
                room_name=room_name,
                confidence=0.6,
                direction=None,
                bbox=None,
                source="ha_sensor",
            )
            await self._update_location_state(
                db=db,
                person_id=sighting.person_id,
                room_name=room_name,
                sensor_id=sensor.id,
                confidence=0.6,
                source="ha_sensor",
            )
            break

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _record_sighting(
        self,
        db: Session,
        person_id: str,
        sensor_id: str,
        room_name: str,
        confidence: float,
        direction: str | None,
        bbox: list[float] | None,
        source: str,
    ) -> None:
        """Insert a :class:`~backend.models.person.PersonSighting` row."""
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

        from backend.models.room import Room

        room = db.query(Room).filter(Room.name == room_name).first()
        room_id = room.id if room else None

        sighting = PersonSighting(
            person_id=person_id,
            sensor_id=sensor_id,
            room_id=room_id,
            room_name=room_name,
            confidence=confidence,
            direction=direction,
            bbox_json={"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]}
            if bbox
            else None,
            source=source,
        )
        db.add(sighting)
        db.commit()

    async def _update_location_state(
        self,
        db: Session,
        person_id: str,
        room_name: str,
        sensor_id: str,
        confidence: float,
        source: str,
        room_transition: RoomTransition | None = None,
    ) -> None:
        """Upsert :class:`~backend.models.person.PersonLocationState` and append
        to :class:`~backend.models.person.PersonLocationHistory` on room change.

        When *room_transition* is provided its ``direction_semantic`` /
        ``from_room_*`` fields are stored on the new history row.
        """
        from backend.models.room import Room

        now = datetime.now(UTC)
        room = db.query(Room).filter(Room.name == room_name).first()
        room_id = room.id if room else None

        loc = (
            db.query(PersonLocationState).filter(PersonLocationState.person_id == person_id).first()
        )

        if loc:
            if room_name != loc.current_room_name:
                # Close the open history entry for the previous room.
                prev = (
                    db.query(PersonLocationHistory)
                    .filter(
                        PersonLocationHistory.person_id == person_id,
                        PersonLocationHistory.exited_at.is_(None),
                    )
                    .first()
                )
                if prev:
                    prev.exited_at = now
                    db.flush()

                db.add(
                    _make_history_entry(
                        person_id=person_id,
                        room_id=room_id,
                        room_name=room_name,
                        entered_at=now,
                        source=source,
                        room_transition=room_transition,
                    )
                )

            loc.current_room_id = room_id
            loc.current_room_name = room_name
            loc.last_seen_at = now
            loc.last_sensor_id = sensor_id
            loc.status = "home"
            loc.confidence = confidence
        else:
            db.add(
                PersonLocationState(
                    person_id=person_id,
                    current_room_id=room_id,
                    current_room_name=room_name,
                    last_seen_at=now,
                    last_sensor_id=sensor_id,
                    status="home",
                    confidence=confidence,
                )
            )
            db.add(
                _make_history_entry(
                    person_id=person_id,
                    room_id=room_id,
                    room_name=room_name,
                    entered_at=now,
                    source=source,
                    room_transition=room_transition,
                )
            )

        db.commit()

        if self._ha_propagation:
            await self._propagate_to_ha(person_id, room_name, confidence)

    async def _propagate_to_ha(self, person_id: str, room_name: str, confidence: float) -> None:
        """Push person location to Home Assistant as an input_text helper."""
        try:
            await self._ha.set_person_location(person_id, room_name, confidence)
        except Exception:
            logger.warning("ha_propagation_failed", person_id=person_id)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def get_person_locations(self) -> list[dict]:
        """Return current location of all active tracked persons."""
        db: Session = self._db_factory()
        try:
            rows = (
                db.query(PersonLocationState, HouseholdMember)
                .join(HouseholdMember, PersonLocationState.person_id == HouseholdMember.id)
                .filter(HouseholdMember.is_active.is_(True))
                .all()
            )
            return [
                {
                    "person_id": state.person_id,
                    "person_name": member.name,
                    "current_room_name": state.current_room_name,
                    "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
                    "last_sensor_id": state.last_sensor_id,
                    "status": state.status,
                    "confidence": state.confidence,
                }
                for state, member in rows
            ]
        finally:
            db.close()

    async def get_person_location(self, person_id: str) -> dict | None:
        """Return current location of a specific person."""
        db: Session = self._db_factory()
        try:
            result = (
                db.query(PersonLocationState, HouseholdMember)
                .join(HouseholdMember, PersonLocationState.person_id == HouseholdMember.id)
                .filter(PersonLocationState.person_id == person_id)
                .first()
            )
            if not result:
                return None
            state, member = result
            return {
                "person_id": state.person_id,
                "person_name": member.name,
                "current_room_name": state.current_room_name,
                "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
                "last_sensor_id": state.last_sensor_id,
                "status": state.status,
                "confidence": state.confidence,
            }
        finally:
            db.close()

    async def get_location_history(self, person_id: str, hours: float = 24.0) -> list[dict]:
        """Return location timeline for a person."""
        db: Session = self._db_factory()
        try:
            cutoff = datetime.now(UTC) - timedelta(hours=hours)
            entries = (
                db.query(PersonLocationHistory)
                .filter(
                    PersonLocationHistory.person_id == person_id,
                    PersonLocationHistory.entered_at >= cutoff,
                )
                .order_by(desc(PersonLocationHistory.entered_at))
                .all()
            )
            return [
                {
                    "id": e.id,
                    "person_id": e.person_id,
                    "room_name": e.room_name,
                    "entered_at": e.entered_at.isoformat(),
                    "exited_at": e.exited_at.isoformat() if e.exited_at else None,
                    "source": e.source,
                    "direction_semantic": e.direction_semantic,
                    "from_room_name": e.from_room_name,
                }
                for e in entries
            ]
        finally:
            db.close()

    async def get_recent_sightings(self, person_id: str, limit: int = 20) -> list[dict]:
        """Return recent sightings for a person."""
        db: Session = self._db_factory()
        try:
            sightings = (
                db.query(PersonSighting)
                .filter(PersonSighting.person_id == person_id)
                .order_by(desc(PersonSighting.timestamp))
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": s.id,
                    "person_id": s.person_id,
                    "sensor_id": s.sensor_id,
                    "room_name": s.room_name,
                    "timestamp": s.timestamp.isoformat(),
                    "confidence": s.confidence,
                    "direction": s.direction,
                    "source": s.source,
                }
                for s in sightings
            ]
        finally:
            db.close()

    async def record_activity(
        self,
        person_id: str,
        activity_type: str,
        room_name: str | None,
        confidence: float,
        source_event_id: int | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record a detected activity for a person."""
        from backend.models.room import Room

        db: Session = self._db_factory()
        try:
            room_id: int | None = None
            if room_name:
                room = db.query(Room).filter(Room.name == room_name).first()
                room_id = room.id if room else None

            db.add(
                PersonActivity(
                    person_id=person_id,
                    activity_type=activity_type,
                    room_id=room_id,
                    room_name=room_name,
                    confidence=confidence,
                    source_event_id=source_event_id,
                    metadata_json=metadata,
                )
            )
            db.commit()
            logger.info(
                "activity_recorded",
                person_id=person_id,
                activity_type=activity_type,
                room=room_name,
            )
        except Exception:
            db.rollback()
            logger.exception("record_activity_error", person_id=person_id)
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
            except Exception:
                logger.warning("failed_to_load_image", path=path[:100])
        return images


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _make_history_entry(
    *,
    person_id: str,
    room_id: int | None,
    room_name: str,
    entered_at: datetime,
    source: str,
    room_transition: RoomTransition | None,
) -> PersonLocationHistory:
    """Construct a :class:`PersonLocationHistory` row, optionally enriched with
    topology-derived fields from *room_transition*."""
    return PersonLocationHistory(
        person_id=person_id,
        room_id=room_id,
        room_name=room_name,
        entered_at=entered_at,
        source=source,
        direction_semantic=room_transition.semantic if room_transition else None,
        from_room_id=room_transition.from_room_id if room_transition else None,
        from_room_name=room_transition.from_room_name if room_transition else None,
    )
