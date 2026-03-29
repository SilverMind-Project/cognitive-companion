"""
Sensor polling service - periodically queries Home Assistant for presence
sensors, tracks room occupancy, and fires occupancy_duration rules through
the workflow pipeline when configured thresholds are reached.

Occupancy safety logic (e.g. "bathroom occupied for > 40 min") is now
expressed as ordinary rules with trigger_type="occupancy_duration" rather
than being hardcoded here. The pipeline handles alert creation, notification
dispatch, and language translation through the standard step and channel
plugins.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.homeassistant import HomeAssistantClient
from backend.models.sensor import Sensor

logger = get_logger(__name__)


class SensorPollingService:
    """Polls HA presence sensors, tracks occupancy durations, and fires
    occupancy_duration rules through the workflow pipeline."""

    def __init__(
        self,
        db_session_factory,
        ha_client: HomeAssistantClient,
        workflow_pipeline=None,
    ) -> None:
        self._db_factory = db_session_factory
        self._ha = ha_client
        self._workflow_pipeline = workflow_pipeline
        # Track active occupancy per sensor: sensor_id -> start_time
        self._active_occupancy: dict[str, datetime] = {}

    async def poll(self) -> None:
        """Run one polling cycle for all enabled presence sensors."""
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
                await self._poll_sensor(sensor, db)
        except Exception:
            logger.exception("sensor_polling_error")
        finally:
            db.close()

    async def _poll_sensor(self, sensor: Sensor, db: Session) -> None:
        """Poll a single presence sensor and handle occupancy logic."""
        ha_entity = sensor.ha_entity_id
        if not ha_entity:
            ha_entity = f"binary_sensor.{sensor.id}_person_information"

        try:
            state_data = await self._ha.get_entity_state(ha_entity)
            state = state_data.get("state", "off") if state_data else "off"
        except Exception:
            logger.warning("sensor_poll_failed", sensor_id=sensor.id)
            return

        room_name = sensor.room.name if sensor.room else "Unknown"
        now = datetime.now(UTC)

        if state == "on":
            if sensor.id not in self._active_occupancy:
                self._active_occupancy[sensor.id] = now
                logger.info("occupancy_started", sensor=sensor.id, room=room_name)
            else:
                start = self._active_occupancy[sensor.id]
                duration = now - start
                elapsed_minutes = duration.total_seconds() / 60
                await self._check_occupancy_rules(
                    sensor, room_name, elapsed_minutes, db
                )
        elif state == "off" and sensor.id in self._active_occupancy:
            del self._active_occupancy[sensor.id]
            logger.info("occupancy_ended", sensor=sensor.id, room=room_name)

    async def _check_occupancy_rules(
        self,
        sensor: Sensor,
        room_name: str,
        elapsed_minutes: float,
        db: Session,
    ) -> None:
        """Fire occupancy_duration rules for this sensor via the pipeline."""
        if not self._workflow_pipeline:
            return
        await self._workflow_pipeline.process_occupancy_event(
            sensor=sensor,
            room_name=room_name,
            duration_minutes=elapsed_minutes,
            db=db,
        )

    async def get_occupancy_summary(self) -> dict[str, dict]:
        """Return current occupancy state for all tracked sensors.

        Returns dict of sensor_id -> {"room": ..., "occupied": bool, "since": iso}.
        Used by the MCP/API layer.
        """
        result: dict[str, dict] = {}
        db: Session = self._db_factory()
        try:
            sensors = (
                db.query(Sensor)
                .filter(Sensor.sensor_type == "presence", Sensor.enabled.is_(True))
                .all()
            )
            for sensor in sensors:
                room_name = sensor.room.name if sensor.room else "Unknown"
                since = self._active_occupancy.get(sensor.id)
                result[sensor.id] = {
                    "room": room_name,
                    "occupied": since is not None,
                    "since": since.isoformat() if since else None,
                }
        finally:
            db.close()
        return result

    async def get_room_occupancy_timeseries(
        self,
        room_name: str,
        hours: float = 2.0,
    ) -> list[dict]:
        """Get smoothed occupancy time-series for a room from HA history.

        Queries the presence sensor(s) assigned to the room and applies
        noise smoothing.
        """
        db: Session = self._db_factory()
        try:
            sensors = (
                db.query(Sensor)
                .filter(
                    Sensor.sensor_type == "presence",
                    Sensor.enabled.is_(True),
                )
                .all()
            )
            # Find sensors in the target room
            target_sensors = [
                s for s in sensors
                if s.room and s.room.name.lower() == room_name.lower()
            ]
        finally:
            db.close()

        if not target_sensors:
            return []

        all_ranges: list[dict] = []
        for sensor in target_sensors:
            entity_id = sensor.ha_entity_id or f"binary_sensor.{sensor.id}_person_information"
            history = await self._ha.get_state_history(entity_id, hours=hours)
            smoothed = self._ha.smooth_occupancy(history)
            all_ranges.extend(smoothed)

        return all_ranges
