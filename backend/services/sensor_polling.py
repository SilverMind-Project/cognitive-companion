"""
Sensor polling service – periodically queries Home Assistant for presence
sensors, tracks room occupancy, and raises emergency alerts.

Unlike the original v1 implementation, occupancy data is fetched from
Home Assistant's time-series history and smoothed to eliminate noise.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.homeassistant import HomeAssistantClient
from backend.models.alert import EmergencyAlert
from backend.models.sensor import Sensor

logger = get_logger(__name__)


class SensorPollingService:
    """Polls HA presence sensors and manages occupancy-based alerts."""

    def __init__(
        self,
        db_session_factory,
        ha_client: HomeAssistantClient,
        ws_manager=None,
    ) -> None:
        self._db_factory = db_session_factory
        self._ha = ha_client
        self._ws_manager = ws_manager
        self._bathroom_limit = settings.get(
            "homeassistant.bathroom_time_limit_minutes", 20
        )
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
                # Check duration limits
                start = self._active_occupancy[sensor.id]
                duration = now - start
                await self._check_occupancy_alerts(
                    sensor, room_name, duration, db
                )
        elif state == "off":
            if sensor.id in self._active_occupancy:
                del self._active_occupancy[sensor.id]
                logger.info("occupancy_ended", sensor=sensor.id, room=room_name)

    async def _check_occupancy_alerts(
        self,
        sensor: Sensor,
        room_name: str,
        duration: timedelta,
        db: Session,
    ) -> None:
        """Check if occupancy duration exceeds configured limits."""
        # Bathroom safety check
        if (
            "bathroom" in room_name.lower()
            and duration > timedelta(minutes=self._bathroom_limit)
        ):
            # Don't re-alert if there's already an unresolved alert
            existing = (
                db.query(EmergencyAlert)
                .filter(
                    EmergencyAlert.sensor_id == sensor.id,
                    EmergencyAlert.room_name == room_name,
                    EmergencyAlert.resolved.is_(False),
                )
                .first()
            )
            if existing:
                return

            alert = EmergencyAlert(
                alert_type="bathroom_time_exceeded",
                description=(
                    f"Person has been in the {room_name} for over "
                    f"{self._bathroom_limit} minutes."
                ),
                sensor_id=sensor.id,
                room_name=room_name,
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)

            logger.warning("emergency_alert_created", alert_id=alert.id, room=room_name)

            # Broadcast to connected clients
            if self._ws_manager:
                await self._ws_manager.broadcast({
                    "type": "emergency_alert",
                    "alert_id": alert.id,
                    "message": alert.description,
                    "room": room_name,
                })

                # Queue a voice prompt for the realtime backend
                prompt = (
                    f"The following emergency alert was generated: {alert.description}. "
                    "Ask the user if they need assistance and if so, click on the "
                    '"need assistance" button in the app to notify caregivers. '
                    "Ask in simple colloquial Tamil."
                )

                async def _alert_callback(response_text: str):
                    logger.info(
                        "alert_voice_response",
                        alert_id=alert.id,
                        response=response_text[:100],
                    )

                await self._ws_manager.send_backend_task(
                    prompt=prompt, callback=_alert_callback
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
