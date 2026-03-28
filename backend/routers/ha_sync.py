"""
Home Assistant sync router: import rooms, sensors, and media players from HA.
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

# Maps HA entity domain prefixes to Sensor.sensor_type values.
_SENSOR_TYPE_MAP: dict[str, str] = {
    "media_player": "media_player",
}


def _infer_sensor_type(entity_id: str) -> str:
    """Infer the sensor_type from an entity_id string."""
    if "person_information" in entity_id or "presence" in entity_id:
        return "presence"
    if "illuminance" in entity_id or "light" in entity_id:
        return "light"
    if "heartbeat" in entity_id or "breathing" in entity_id:
        return "presence"
    if "distance" in entity_id:
        return "distance"
    domain = entity_id.split(".")[0] if "." in entity_id else ""
    return _SENSOR_TYPE_MAP.get(domain, "generic")


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

    Discovers entities in HA areas and creates or updates Sensor records for
    binary_sensor, sensor, and media_player domain entities.  The sensor's
    room_id is set or updated on every sync run so that room reassignments in
    HA are reflected locally.
    """
    ha_client = getattr(request.app.state, "ha_client", None)
    if ha_client is None or not ha_client.configured:
        return {"error": "Home Assistant not configured"}

    # Determine which rooms to sync
    if room_name:
        rooms = db.query(Room).filter(Room.name == room_name).all()
    else:
        rooms = db.query(Room).filter(Room.ha_area_id.isnot(None)).all()

    created, updated, skipped = 0, 0, 0
    allowed_domains = {"sensor", "binary_sensor", "media_player"}

    for room in rooms:
        if not room.ha_area_id:
            continue
        entities = await ha_client.get_entities_for_area(room.ha_area_id)

        for entity in entities:
            entity_id = entity.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""

            if domain not in allowed_domains:
                continue

            sensor_type = _infer_sensor_type(entity_id)
            friendly_name = entity.get("attributes", {}).get("friendly_name", entity_id)

            existing = db.query(Sensor).filter(Sensor.ha_entity_id == entity_id).first()
            if existing:
                # Update room association and name so HA renames/moves are reflected.
                existing.room_id = room.id
                existing.name = friendly_name
                updated += 1
            else:
                sensor = Sensor(
                    id=entity_id,
                    name=friendly_name,
                    room_id=room.id,
                    sensor_type=sensor_type,
                    source="homeassistant",
                    ha_entity_id=entity_id,
                    enabled=True,
                )
                db.add(sensor)
                created += 1

    db.commit()
    logger.info("ha_sensors_synced", created=created, updated=updated, skipped=skipped)
    return {"created": created, "updated": updated, "skipped": skipped}


@router.get("/media-players")
async def list_media_players(
    request: Request,
    auth: AuthContext = Depends(require_permission("admin")),
):
    """Return all media_player entity IDs from Home Assistant.

    Used by the pipeline step config UI to populate the TTS media player
    dropdown without requiring a full sensor sync.
    """
    ha_client = getattr(request.app.state, "ha_client", None)
    if ha_client is None or not ha_client.configured:
        return []

    players = await ha_client.get_media_players()
    return [
        {
            "entity_id": p["entity_id"],
            "name": p.get("attributes", {}).get("friendly_name", p["entity_id"]),
        }
        for p in players
    ]


@router.get("/entities")
async def list_entities(
    request: Request,
    domain: str | None = None,
    auth: AuthContext = Depends(require_permission("admin")),
):
    """Return HA entity IDs, optionally filtered by domain.

    Used by the ha_action step config UI to populate the entity_id dropdown.
    Pass ``?domain=light`` to get only light entities, etc.
    """
    ha_client = getattr(request.app.state, "ha_client", None)
    if ha_client is None or not ha_client.configured:
        return []

    if domain:
        entities = await ha_client.get_entities_by_domain(domain)
    else:
        # Return a lightweight list from the DB (HA-sourced sensors) to avoid
        # fetching all HA states when no domain filter is given.
        db_gen = request.app.dependency_overrides.get(get_db)
        # Fallback: return empty list rather than hitting HA without a filter
        return []

    return [
        {
            "entity_id": e["entity_id"],
            "name": e.get("attributes", {}).get("friendly_name", e["entity_id"]),
        }
        for e in entities
    ]
