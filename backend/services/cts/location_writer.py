"""LocationWriter: CTS writer for PersonLocationState / PersonLocationHistory.

Consumes decoded tracking events (dicts produced by
:class:`backend.services.cts.tracking_event_subscriber.TrackingEventSubscriber`)
and applies them to the canonical person-location tables via a
:class:`LocationRepository`.

Behaviour
---------
- Upserts :class:`PersonLocationState` per ``person_id``.
- Appends :class:`PersonLocationHistory` on room change and closes the
  previous open row with ``exited_at=event_time``.
- Uses the :class:`SourceAuthority` helper to decide whether the CTS event
  is allowed to overwrite the current state (presence-sensor events and
  scene-analysis events may beat CTS in some deployments).
- Every history row written carries ``source="cts"``, ``global_track_id``
  from the event, and a nullable ``superseded_by_revision_id`` that
  :class:`IdentityRewriter` fills in when an identity revision arrives.

This service delegates all persistence to the injected
:class:`LocationRepository`, keeping the writer free of direct ORM calls.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.models.person import PersonLocationState
from backend.services.cts._time import parse_ts
from backend.services.cts.source_authority import SourceAuthority
from backend.services.occupancy_writer import upsert_room_occupancy

logger = get_logger(__name__)


class LocationWriter:
    """Writes CTS tracking events to the person-location tables.

    Parameters
    ----------
    repo_factory:
        Callable that returns a fresh :class:`LocationRepository` instance.
        In production this wraps ``SqlAlchemyLocationRepository(get_session())``.
        In tests it returns :class:`InMemoryLocationRepository`.
    authority:
        Source-authority policy. Defaults to :class:`SourceAuthority`
        configured to favor CTS over sensor-inferred sources.
    """

    SOURCE = "cts"

    def __init__(
        self,
        repo_factory,
        authority: SourceAuthority | None = None,
        camera_room_map: dict[str, str] | None = None,
        db_factory=None,
    ) -> None:
        self._repo_factory = repo_factory
        self._authority = authority or SourceAuthority()
        self._camera_room_map: dict[str, str] = camera_room_map or {}
        # Optional separate DB factory for occupancy writes after location commit.
        self._db_factory = db_factory

    async def apply(self, event: dict[str, Any]) -> list[str]:
        """Apply one decoded tracking event. Returns the list of person_ids
        touched so the caller can broadcast location updates on the WS.
        """
        detections = event.get("detections") or []
        camera_id = event.get("camera_id") or ""
        # Fall back to the camera's configured room when the orchestrator
        # omits room_name from the proto (common for single-camera deployments).
        room_name = event.get("room_name") or self._camera_room_map.get(camera_id) or None
        event_time = (
            parse_ts(event.get("event_time")) if event.get("event_time") else datetime.now(UTC)
        )

        touched: list[str] = []
        # Rooms that need occupancy state refresh after the location commit.
        affected_rooms: set[str] = set()

        repo = self._repo_factory()
        try:
            for det in detections:
                person_id = (det.get("identity_id") or "").strip()
                if not person_id:
                    continue
                global_track_id = det.get("global_track_id") or None
                confidence = float(det.get("identity_confidence") or 0.0)

                current = repo.get_state(person_id)

                if current is not None and not self._authority.cts_supersedes(
                    current_source=current.last_sensor_id or "",
                    current_updated_at=current.updated_at,
                    event_time=event_time,
                ):
                    # A more authoritative source recently wrote state; skip.
                    continue

                changed_room = current is None or (
                    room_name is not None and room_name != current.current_room_name
                )

                # Persist the source prefix so :class:`SourceAuthority` can
                # distinguish CTS-owned state from other providers later.
                stamped_sensor_id = f"cts:{camera_id}" if camera_id else "cts"

                repo.upsert_state(
                    person_id=person_id,
                    room_name=room_name or (current.current_room_name if current else None),
                    sensor_id=stamped_sensor_id,
                    confidence=confidence,
                    status="home",
                    event_time=event_time,
                )

                if changed_room and room_name:
                    # Track the previous room so we can refresh its occupancy.
                    if current and current.current_room_name:
                        affected_rooms.add(current.current_room_name)
                    affected_rooms.add(room_name)

                    # Close the open prior row for this person.
                    repo.close_open_history(
                        person_id,
                        exited_at=event_time,
                        require_no_superseded=True,
                    )

                    repo.append_history(
                        person_id=person_id,
                        room_name=room_name,
                        entered_at=event_time,
                        source=self.SOURCE,
                        global_track_id=global_track_id,
                    )

                touched.append(person_id)

            if touched:
                repo.commit()
                logger.info(
                    "cts_location_write",
                    event_camera=camera_id,
                    touched=touched,
                    room=room_name,
                )
            else:
                repo.rollback()
        except Exception:
            repo.rollback()
            logger.exception("cts_location_write_error")
            raise
        finally:
            repo.close()

        if touched and affected_rooms and self._db_factory:
            self._sync_room_occupancy(affected_rooms)

        return touched

    def _sync_room_occupancy(self, rooms: set[str]) -> None:
        """Refresh RoomOccupancyState for *rooms* based on current PersonLocationState."""
        db = self._db_factory()
        try:
            for room in rooms:
                persons = (
                    db.query(PersonLocationState)
                    .filter(PersonLocationState.current_room_name == room)
                    .all()
                )
                # Exclude anonymous/unknown tracks from the identified persons list.
                identified = [
                    p.person_id
                    for p in persons
                    if p.person_id and not p.person_id.startswith("unknown")
                ]
                occupied = len(persons) > 0
                upsert_room_occupancy(
                    db,
                    room_name=room,
                    occupied=occupied,
                    source="cts",
                    person_ids=identified,
                )
        except Exception:
            logger.exception("cts_occupancy_sync_error")
            with contextlib.suppress(Exception):
                db.rollback()
        finally:
            db.close()
