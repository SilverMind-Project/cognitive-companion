"""LocationWriter: CTS writer for PersonLocationState / PersonLocationHistory.

Consumes decoded tracking events (dicts produced by
:class:`backend.services.cts.tracking_event_subscriber.TrackingEventSubscriber`)
and applies them to the canonical person-location tables.

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

This service is read-free on the hot path: it reads only the current state
row for the identity, which is already indexed by ``person_id``.  It is
safe to call concurrently from multiple subscribers because the
per-identity upsert sequence is short and SQLite's default isolation is
SERIALIZABLE for in-transaction writes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.models.person import PersonLocationHistory, PersonLocationState
from backend.services.cts.source_authority import SourceAuthority

logger = get_logger(__name__)


class LocationWriter:
    """Writes CTS tracking events to the person-location tables.

    Parameters
    ----------
    db_factory:
        Callable that returns a new SQLAlchemy ``Session``. Matches the
        signature used by :class:`SignalStore`.
    authority:
        Source-authority policy. Defaults to :class:`SourceAuthority`
        configured to favor CTS over sensor-inferred sources.
    """

    SOURCE = "cts"

    def __init__(
        self,
        db_factory,  # type: ignore[no-untyped-def]
        authority: SourceAuthority | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._authority = authority or SourceAuthority()

    async def apply(self, event: dict[str, Any]) -> list[str]:
        """Apply one decoded tracking event. Returns the list of person_ids
        touched so the caller can broadcast location updates on the WS.
        """
        detections = event.get("detections") or []
        room_name = event.get("room_name") or None
        camera_id = event.get("camera_id") or ""
        event_time = _parse_ts(event.get("event_time")) if event.get("event_time") else datetime.now(UTC)

        touched: list[str] = []

        db = self._db_factory()
        try:
            for det in detections:
                person_id = (det.get("identity_id") or "").strip()
                if not person_id:
                    continue
                global_track_id = det.get("global_track_id") or None
                confidence = float(det.get("identity_confidence") or 0.0)

                current = (
                    db.query(PersonLocationState)
                    .filter(PersonLocationState.person_id == person_id)
                    .first()
                )

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
                stamped_sensor_id = (
                    f"cts:{camera_id}" if camera_id else "cts"
                )
                if current is None:
                    current = PersonLocationState(
                        person_id=person_id,
                        current_room_name=room_name,
                        last_seen_at=event_time,
                        last_sensor_id=stamped_sensor_id,
                        status="home",
                        confidence=confidence,
                        updated_at=event_time,
                    )
                    db.add(current)
                else:
                    current.current_room_name = room_name or current.current_room_name
                    current.last_seen_at = event_time
                    current.last_sensor_id = stamped_sensor_id
                    current.status = "home"
                    current.confidence = confidence
                    current.updated_at = event_time

                if changed_room and room_name:
                    # Close the open prior row for this person.
                    prev = (
                        db.query(PersonLocationHistory)
                        .filter(
                            PersonLocationHistory.person_id == person_id,
                            PersonLocationHistory.exited_at.is_(None),
                            PersonLocationHistory.superseded_by_revision_id.is_(None),
                        )
                        .order_by(PersonLocationHistory.entered_at.desc())
                        .first()
                    )
                    if prev is not None:
                        prev.exited_at = event_time

                    db.add(
                        PersonLocationHistory(
                            person_id=person_id,
                            room_name=room_name,
                            entered_at=event_time,
                            source=self.SOURCE,
                            global_track_id=global_track_id,
                        )
                    )

                touched.append(person_id)

            if touched:
                db.commit()
                logger.info(
                    "cts_location_write",
                    event_camera=camera_id,
                    touched=touched,
                    room=room_name,
                )
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception("cts_location_write_error")
            raise
        finally:
            db.close()

        return touched


def _parse_ts(value: str | datetime) -> datetime:
    """Normalise an ISO-8601 string or datetime to a tz-aware UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
