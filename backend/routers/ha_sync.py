"""
Home Assistant sync router – imports rooms and sensors from HA.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.room import Room
from backend.models.sensor import Sensor

logger = get_logger(__name__)

router = APIRouter(prefix="/ha", tags=["homeassistant"])


@router.post("/sync/rooms")
async def sync_rooms(
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("admin")),
):
    """Import rooms (areas) from Home Assistant into the local database.

    Existing rooms with matching ha_area_id are updated; new rooms are created.
    """
    ha_client = getattr(request.app.state, "ha_client", None)
    if ha_client is None or not ha_client.configured:
        return {"error": "Home Assistant not configured"}

    areas = await ha_client.get_areas()
    created, updated = 0, 0

    for area in areas:
        existing = db.query(Room).filter(Room.ha_area_id == area["area_id"]).first()
        if existing:
            existing.name = area["name"]
            updated += 1
        else:
            room = Room(
                name=area["name"],
                ha_area_id=area["area_id"],
                floor=area.get("floor"),
            )
            db.add(room)
            created += 1

    db.commit()
    logger.info("ha_rooms_synced", created=created, updated=updated)
    return {"created": created, "updated": updated, "total_areas": len(areas)}


@router.post("/sync/sensors")
async def sync_sensors(
    request: Request,
    room_name: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("admin")),
):
    """Import sensors from Home Assistant for a room (or all rooms).

    Discovers entities in HA areas and creates Sensor records for
    binary_sensor and sensor domain entities.
    """
    ha_client = getattr(request.app.state, "ha_client", None)
    if ha_client is None or not ha_client.configured:
        return {"error": "Home Assistant not configured"}

    # Determine which rooms to sync
    if room_name:
        rooms = db.query(Room).filter(Room.name == room_name).all()
    else:
        rooms = db.query(Room).filter(Room.ha_area_id.isnot(None)).all()

    created, skipped = 0, 0

    for room in rooms:
        if not room.ha_area_id:
            continue
        entities = await ha_client.get_entities_for_area(room.ha_area_id)

        for entity in entities:
            entity_id = entity.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""

            # Only import sensor and binary_sensor entities
            if domain not in ("sensor", "binary_sensor"):
                continue

            # Determine sensor type
            sensor_type = "generic"
            if "person_information" in entity_id or "presence" in entity_id:
                sensor_type = "presence"
            elif "illuminance" in entity_id or "light" in entity_id:
                sensor_type = "light"
            elif "heartbeat" in entity_id or "breathing" in entity_id:
                sensor_type = "presence"
            elif "distance" in entity_id:
                sensor_type = "distance"

            # Check if already exists
            existing = db.query(Sensor).filter(
                Sensor.ha_entity_id == entity_id
            ).first()
            if existing:
                skipped += 1
                continue

            sensor = Sensor(
                id=entity_id,
                name=entity.get("attributes", {}).get(
                    "friendly_name", entity_id
                ),
                room_id=room.id,
                sensor_type=sensor_type,
                source="homeassistant",
                ha_entity_id=entity_id,
                enabled=True,
            )
            db.add(sensor)
            created += 1

    db.commit()
    logger.info("ha_sensors_synced", created=created, skipped=skipped)
    return {"created": created, "skipped": skipped}
