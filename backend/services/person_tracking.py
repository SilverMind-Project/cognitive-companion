"""Person location tracking service.

Fuses camera-based person identification with Home Assistant presence sensors
to maintain a real-time model of where each household member is located.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.homeassistant import HomeAssistantClient
from backend.integrations.person_id_client import PersonIDClient, FaceResult, MotionResult
from backend.models.person import (
    HouseholdMember,
    PersonActivity,
    PersonLocationHistory,
    PersonLocationState,
    PersonSighting,
)
from backend.models.sensor import Sensor

logger = get_logger(__name__)


@dataclass
class PersonDetection:
    person_id: str
    name: str
    confidence: float
    bbox: list[float]
    direction: str | None = None

    def dict(self) -> dict:
        return {
            "person_id": self.person_id,
            "name": self.name,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "direction": self.direction,
        }


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
        self._stale_minutes = settings.get("person_tracking.location_stale_minutes", 30)
        self._ha_propagation = settings.get("person_tracking.ha_propagation", True)
        self._min_confidence = settings.get("person_id.min_confidence", 0.5)

    async def process_camera_event(
        self,
        sensor_id: str,
        media_paths: list[str],
        room_name: str,
        include_annotated_image: bool = False,
    ) -> list[PersonDetection]:
        """Process a camera event through the person-id service.

        Called by the workflow pipeline before the expensive VLLM vision step.

        1. Downloads images from media_paths (presigned MinIO URLs or local paths)
        2. Sends them to the person-id service for identification + motion detection
        3. Records sightings in the database
        4. Updates location state and history
        5. Optionally propagates to Home Assistant

        Returns list of PersonDetection for use by the workflow pipeline.
        """
        if not self._person_id.enabled:
            return []

        # Encode images to base64 for the person-id service
        images_b64 = await self._load_images_as_base64(media_paths)
        if not images_b64:
            return []

        include_motion = settings.get("person_id.include_motion", True)
        batch_result = await self._person_id.identify_batch(
            images_b64,
            include_motion=include_motion,
            include_annotated_image=include_annotated_image,
        )
        if not batch_result:
            return []

        # Build a direction lookup from motion results
        direction_map: dict[str, str] = {}
        for m in batch_result.motion:
            direction_map[m.person_id] = m.direction

        # Deduplicate detections across frames: keep the highest confidence per person
        best_detections: dict[str, PersonDetection] = {}
        for frame_faces in batch_result.frames:
            for face in frame_faces:
                if face.confidence < self._min_confidence:
                    continue
                existing = best_detections.get(face.person_id)
                if not existing or face.confidence > existing.confidence:
                    best_detections[face.person_id] = PersonDetection(
                        person_id=face.person_id,
                        name=face.name,
                        confidence=face.confidence,
                        bbox=face.bbox,
                        direction=direction_map.get(face.person_id),
                    )

        detections = list(best_detections.values())

        # Record sightings and update location state
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
                )
        finally:
            db.close()

        return detections

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
            if not sensors:
                return

            for sensor in sensors:
                await self._correlate_presence_sensor(sensor, db)
        except Exception:
            logger.exception("person_tracking_poll_error")
        finally:
            db.close()

    async def _correlate_presence_sensor(self, sensor: Sensor, db: Session) -> None:
        """When a presence sensor reads "on", try to infer who is there."""
        ha_entity = sensor.ha_entity_id
        if not ha_entity:
            ha_entity = f"binary_sensor.{sensor.id}_person_information"

        try:
            state_data = await self._ha.get_entity_state(ha_entity)
            state = state_data.get("state", "off") if state_data else "off"
        except Exception:
            return

        if state != "on":
            return

        room_name = sensor.room.name if sensor.room else "Unknown"
        now = datetime.now(timezone.utc)

        # Find the person most recently seen near this room
        # Look at recent sightings (last 10 minutes) sorted by recency
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

        # Find persons who are not already known to be in another room
        # and were most recently seen, prioritizing those near this room
        for sighting in recent_sightings:
            loc_state = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == sighting.person_id)
                .first()
            )
            # If person is already confirmed in this room, skip
            if loc_state and loc_state.current_room_name == room_name:
                continue
            # If person was last seen in a different room very recently by camera, skip
            if (
                loc_state
                and loc_state.current_room_name != room_name
                and loc_state.last_seen_at
                and (now - loc_state.last_seen_at).total_seconds() < 60
            ):
                continue

            # Infer this person is in the presence-sensor room
            await self._record_sighting(
                db=db,
                person_id=sighting.person_id,
                sensor_id=sensor.id,
                room_name=room_name,
                confidence=0.6,  # lower confidence for sensor-inferred
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
            break  # only assign one person per sensor activation

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
        """Record a person sighting in the database."""
        # Ensure the household member exists (auto-register unknowns as guests)
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

        # Find room_id
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
            bbox_json={"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]} if bbox else None,
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
    ) -> None:
        """Update current location state and history for a person."""
        from backend.models.room import Room

        now = datetime.now(timezone.utc)
        room = db.query(Room).filter(Room.name == room_name).first()
        room_id = room.id if room else None

        loc = (
            db.query(PersonLocationState)
            .filter(PersonLocationState.person_id == person_id)
            .first()
        )

        if loc:
            old_room = loc.current_room_name
            # Only update if new detection is more confident or different room
            if room_name != old_room:
                # Close previous location history entry
                prev_history = (
                    db.query(PersonLocationHistory)
                    .filter(
                        PersonLocationHistory.person_id == person_id,
                        PersonLocationHistory.exited_at.is_(None),
                    )
                    .first()
                )
                if prev_history:
                    prev_history.exited_at = now
                    db.flush()

                # Create new history entry
                history = PersonLocationHistory(
                    person_id=person_id,
                    room_id=room_id,
                    room_name=room_name,
                    entered_at=now,
                    source=source,
                )
                db.add(history)

            loc.current_room_id = room_id
            loc.current_room_name = room_name
            loc.last_seen_at = now
            loc.last_sensor_id = sensor_id
            loc.status = "home"
            loc.confidence = confidence
        else:
            loc = PersonLocationState(
                person_id=person_id,
                current_room_id=room_id,
                current_room_name=room_name,
                last_seen_at=now,
                last_sensor_id=sensor_id,
                status="home",
                confidence=confidence,
            )
            db.add(loc)

            # Create initial history entry
            history = PersonLocationHistory(
                person_id=person_id,
                room_id=room_id,
                room_name=room_name,
                entered_at=now,
                source=source,
            )
            db.add(history)

        db.commit()

        # Propagate to Home Assistant
        if self._ha_propagation:
            await self._propagate_to_ha(person_id, room_name, confidence)

    async def _propagate_to_ha(
        self, person_id: str, room_name: str, confidence: float
    ) -> None:
        """Push person location to Home Assistant as an input_text helper."""
        try:
            await self._ha.set_person_location(person_id, room_name, confidence)
        except Exception:
            logger.warning("ha_propagation_failed", person_id=person_id)

    async def get_person_locations(self) -> list[dict]:
        """Return current location of all tracked persons."""
        db: Session = self._db_factory()
        try:
            states = (
                db.query(PersonLocationState, HouseholdMember)
                .join(HouseholdMember, PersonLocationState.person_id == HouseholdMember.id)
                .filter(HouseholdMember.is_active.is_(True))
                .all()
            )
            results = []
            for state, member in states:
                results.append({
                    "person_id": state.person_id,
                    "person_name": member.name,
                    "current_room_name": state.current_room_name,
                    "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
                    "last_sensor_id": state.last_sensor_id,
                    "status": state.status,
                    "confidence": state.confidence,
                })
            return results
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

    async def get_location_history(
        self, person_id: str, hours: float = 24.0
    ) -> list[dict]:
        """Return location timeline for a person."""
        db: Session = self._db_factory()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
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
                }
                for e in entries
            ]
        finally:
            db.close()

    async def get_recent_sightings(
        self, person_id: str, limit: int = 20
    ) -> list[dict]:
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
            room_id = None
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
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            query = db.query(PersonActivity).filter(
                PersonActivity.person_id == person_id,
                PersonActivity.detected_at >= cutoff,
            )
            if activity_type:
                query = query.filter(PersonActivity.activity_type == activity_type)

            activities = (
                query.order_by(desc(PersonActivity.detected_at)).limit(50).all()
            )
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
        person_id: str,
        activity_type: str,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        within_minutes: float | None = None,
        min_confidence: float = 0.0,
    ) -> list[dict]:
        """Query activities within a time window.

        Supports two modes:
        - **Relative**: pass *within_minutes* to query from ``now - minutes`` to now.
        - **Absolute**: pass *window_start* and/or *window_end* as UTC datetimes.

        If both *within_minutes* and explicit window boundaries are provided,
        *within_minutes* takes precedence.
        """
        now = datetime.now(timezone.utc)

        if within_minutes is not None:
            effective_start = now - timedelta(minutes=within_minutes)
            effective_end = now
        else:
            effective_start = window_start
            effective_end = window_end or now

        db: Session = self._db_factory()
        try:
            query = db.query(PersonActivity).filter(
                PersonActivity.person_id == person_id,
                PersonActivity.activity_type == activity_type,
                PersonActivity.confidence >= min_confidence,
            )
            if effective_start:
                query = query.filter(PersonActivity.detected_at >= effective_start)
            if effective_end:
                query = query.filter(PersonActivity.detected_at <= effective_end)

            activities = (
                query.order_by(desc(PersonActivity.detected_at)).limit(50).all()
            )
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
                        b64 = base64.b64encode(resp.content).decode("utf-8")
                        images.append(b64)
                else:
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                        images.append(b64)
            except Exception:
                logger.warning("failed_to_load_image", path=path[:100])
        return images
