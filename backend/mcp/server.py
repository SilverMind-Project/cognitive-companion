"""
MCP (Model Context Protocol) server – exposes read-only tools for AI agents
like OpenClaw to query rooms, sensors, occupancy, images, alerts, and events.

All MCP tool calls are authenticated via API key and checked against the
caller's permissions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.alert import EmergencyAlert
from backend.models.event import EventLog
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.room import Room
from backend.models.rule import Rule
from backend.models.sensor import Sensor

logger = get_logger(__name__)


class MCPToolRegistry:
    """Registry of tools exposed via the MCP protocol.

    Each tool is a callable that accepts keyword arguments and returns
    a JSON-serialisable result. The registry provides metadata (name,
    description, parameters) for tool discovery.
    """

    def __init__(
        self,
        db_session_factory,
        event_aggregator=None,
        sensor_polling_service=None,
        ha_client=None,
        person_tracking=None,
    ) -> None:
        self._db_factory = db_session_factory
        self._aggregator = event_aggregator
        self._sensor_polling = sensor_polling_service
        self._ha = ha_client
        self._person_tracking = person_tracking
        self._tools = self._build_tool_definitions()

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions for MCP discovery."""
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name with the given arguments."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await handler(**arguments)
        except Exception as exc:
            logger.exception("mcp_tool_error", tool=name)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def _tool_get_rooms(self, **kwargs) -> list[dict]:
        """Get all rooms."""
        db: Session = self._db_factory()
        try:
            rooms = db.execute(select(Room)).scalars().all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "ha_area_id": r.ha_area_id,
                    "floor": r.floor,
                }
                for r in rooms
            ]
        finally:
            db.close()

    async def _tool_get_sensors(
        self, room_name: str | None = None, sensor_type: str | None = None, **kwargs
    ) -> list[dict]:
        """Get sensors, optionally filtered by room or type."""
        db: Session = self._db_factory()
        try:
            stmt = select(Sensor)
            if sensor_type:
                stmt = stmt.where(Sensor.sensor_type == sensor_type)
            sensors = db.execute(stmt).scalars().all()

            result = []
            for s in sensors:
                room = s.room.name if s.room else None
                if room_name and room and room.lower() != room_name.lower():
                    continue
                result.append({
                    "id": s.id,
                    "name": s.name,
                    "room": room,
                    "sensor_type": s.sensor_type,
                    "source": s.source,
                    "enabled": s.enabled,
                })
            return result
        finally:
            db.close()

    async def _tool_get_room_occupancy(
        self, room_name: str | None = None, **kwargs
    ) -> dict:
        """Get current room occupancy status."""
        if self._sensor_polling:
            summary = await self._sensor_polling.get_occupancy_summary()
            if room_name:
                return {
                    k: v for k, v in summary.items()
                    if v.get("room", "").lower() == room_name.lower()
                }
            return summary
        return {"message": "Sensor polling not available"}

    async def _tool_get_recent_images(
        self, sensor_id: str, limit: int = 5, **kwargs
    ) -> list[str]:
        """Get recent images from a camera sensor."""
        if self._aggregator:
            return await self._aggregator.get_recent_images(sensor_id, limit=limit)
        return []

    async def _tool_get_light_level(
        self, entity_id: str, **kwargs
    ) -> dict:
        """Get current light level from a HA sensor."""
        if self._ha:
            level = await self._ha.get_light_level(entity_id)
            return {"entity_id": entity_id, "illuminance_lux": level}
        return {"error": "Home Assistant not configured"}

    async def _tool_get_alerts(
        self,
        resolved: bool | None = None,
        room_name: str | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[dict]:
        """Get recent alerts."""
        db: Session = self._db_factory()
        try:
            stmt = select(EmergencyAlert).order_by(EmergencyAlert.timestamp.desc())
            if resolved is not None:
                stmt = stmt.where(EmergencyAlert.resolved == resolved)
            if room_name:
                stmt = stmt.where(EmergencyAlert.room_name == room_name)
            stmt = stmt.limit(limit)

            alerts = db.execute(stmt).scalars().all()
            return [
                {
                    "id": a.id,
                    "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                    "alert_type": a.alert_type,
                    "description": a.description,
                    "room_name": a.room_name,
                    "resolved": a.resolved,
                    "assistance_needed": a.assistance_needed,
                }
                for a in alerts
            ]
        finally:
            db.close()

    async def _tool_get_event_logs(
        self,
        rule_name: str | None = None,
        status: str | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[dict]:
        """Get recent event logs."""
        db: Session = self._db_factory()
        try:
            stmt = select(EventLog).order_by(EventLog.timestamp.desc())
            if rule_name:
                stmt = stmt.where(EventLog.rule_name == rule_name)
            if status:
                stmt = stmt.where(EventLog.status == status)
            stmt = stmt.limit(limit)

            events = db.execute(stmt).scalars().all()
            return [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "rule_name": e.rule_name,
                    "room_name": e.room_name,
                    "status": e.status,
                    "trigger_type": e.trigger_type,
                }
                for e in events
            ]
        finally:
            db.close()

    async def _tool_get_rules(self, enabled_only: bool = True, **kwargs) -> list[dict]:
        """Get rules."""
        db: Session = self._db_factory()
        try:
            stmt = select(Rule)
            if enabled_only:
                stmt = stmt.where(Rule.enabled.is_(True))
            rules = db.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "enabled": r.enabled,
                    "schedule_cron": r.schedule_cron,
                    "cool_off_minutes": r.cool_off_minutes,
                    "max_daily_triggers": r.max_daily_triggers,
                }
                for r in rules
            ]
        finally:
            db.close()

    async def _tool_get_conversation_history(
        self, session_id: int | None = None, limit: int = 20, **kwargs
    ) -> list[dict]:
        """Get recent conversation turns (placeholder – requires ConversationManager)."""
        return [{"message": "Use /api/v1/conversations endpoint for history"}]

    async def _tool_get_person_locations(self, **kwargs) -> list[dict]:
        """Get current location of all tracked household members."""
        if self._person_tracking:
            return await self._person_tracking.get_person_locations()
        return [{"message": "Person tracking not available"}]

    async def _tool_get_person_sightings(
        self, person_id: str, limit: int = 10, **kwargs
    ) -> list[dict]:
        """Get recent camera sightings for a specific person."""
        if self._person_tracking:
            return await self._person_tracking.get_recent_sightings(person_id, limit=limit)
        return [{"message": "Person tracking not available"}]

    async def _tool_get_person_activities(
        self,
        person_id: str,
        activity_type: str | None = None,
        minutes: int = 60,
        **kwargs,
    ) -> list[dict]:
        """Get recent activities for a person."""
        if self._person_tracking:
            return await self._person_tracking.get_recent_activities(
                person_id, activity_type=activity_type, minutes=minutes
            )
        return [{"message": "Person tracking not available"}]

    async def _tool_get_workflow_executions(
        self,
        rule_name: str | None = None,
        status: str | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[dict]:
        """Get recent workflow executions."""
        db: Session = self._db_factory()
        try:
            stmt = select(WorkflowExecution).order_by(WorkflowExecution.started_at.desc())
            if status:
                stmt = stmt.where(WorkflowExecution.status == status)
            stmt = stmt.limit(limit)

            executions = db.execute(stmt).scalars().all()
            results = []
            for ex in executions:
                rule = db.get(Rule, ex.rule_id)
                if rule_name and rule and rule.name != rule_name:
                    continue
                results.append({
                    "id": ex.id,
                    "rule_id": ex.rule_id,
                    "rule_name": rule.name if rule else None,
                    "status": ex.status,
                    "started_at": ex.started_at.isoformat() if ex.started_at else None,
                    "updated_at": ex.updated_at.isoformat() if ex.updated_at else None,
                    "error": ex.error,
                })
            return results
        finally:
            db.close()

    async def _tool_get_rule_pipeline(self, rule_id: int, **kwargs) -> list[dict]:
        """Get pipeline step definitions for a rule."""
        db: Session = self._db_factory()
        try:
            steps = (
                db.query(PipelineStep)
                .filter(PipelineStep.rule_id == rule_id)
                .order_by(PipelineStep.order)
                .all()
            )
            return [
                {
                    "id": s.id,
                    "order": s.order,
                    "step_type": s.step_type,
                    "label": s.label,
                    "config_json": s.config_json,
                    "enabled": s.enabled,
                }
                for s in steps
            ]
        finally:
            db.close()

    async def _tool_trigger_rule(self, rule_id: int, **kwargs) -> dict:
        """Manually trigger a rule's pipeline execution."""
        # This requires the pipeline executor — resolve lazily
        try:
            from backend.services.pipeline_executor import TriggerContext
            from backend.services.scheduler import _pipeline_executor

            if not _pipeline_executor:
                return {"error": "Pipeline executor not available"}

            db: Session = self._db_factory()
            try:
                rule = db.get(Rule, rule_id)
                if not rule:
                    return {"error": f"Rule {rule_id} not found"}

                trigger = TriggerContext(trigger_type="manual", sensor_id=rule.primary_sensor_id)
                execution = await _pipeline_executor.execute(rule, trigger, db)
                return {
                    "execution_id": execution.id,
                    "status": execution.status,
                }
            finally:
                db.close()
        except Exception as exc:
            return {"error": str(exc)}

    async def _tool_get_eink_display_status(
        self, sensor_id: str | None = None, **kwargs
    ) -> list[dict]:
        """Get current e-ink display status for one or all displays."""
        from backend.models.image_state import ActiveImageState

        db: Session = self._db_factory()
        try:
            stmt = select(ActiveImageState)
            if sensor_id:
                stmt = stmt.where(ActiveImageState.sensor_id == sensor_id)
            states = db.execute(stmt).scalars().all()
            now = datetime.now(UTC)
            return [
                {
                    "sensor_id": s.sensor_id,
                    "has_active_image": True,
                    "expired": bool(s.expires_at and s.expires_at < now),
                    "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                    "rendered_text": s.rendered_text,
                }
                for s in states
            ]
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Tool definitions for MCP discovery
    # ------------------------------------------------------------------

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        enabled_tools = settings.get("mcp.tools", [])
        all_tools = [
            {
                "name": "get_rooms",
                "description": "Get all rooms configured in the system",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_sensors",
                "description": "Get sensors, optionally filtered by room_name or sensor_type",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "room_name": {"type": "string", "description": "Filter by room name"},
                        "sensor_type": {"type": "string", "description": "Filter by sensor type (camera, presence, button)"},
                    },
                },
            },
            {
                "name": "get_room_occupancy",
                "description": "Get current room occupancy status from presence sensors",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "room_name": {"type": "string", "description": "Optional room name filter"},
                    },
                },
            },
            {
                "name": "get_recent_images",
                "description": "Get recent images from a camera sensor",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sensor_id": {"type": "string", "description": "Camera sensor ID"},
                        "limit": {"type": "integer", "description": "Max images to return", "default": 5},
                    },
                    "required": ["sensor_id"],
                },
            },
            {
                "name": "get_light_level",
                "description": "Get current light level (illuminance) from a Home Assistant sensor",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "HA entity ID (e.g. sensor.living_room_illuminance)"},
                    },
                    "required": ["entity_id"],
                },
            },
            {
                "name": "get_alerts",
                "description": "Get recent emergency alerts, optionally filtered",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "resolved": {"type": "boolean", "description": "Filter by resolved state"},
                        "room_name": {"type": "string", "description": "Filter by room name"},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            },
            {
                "name": "get_event_logs",
                "description": "Get recent rule execution event logs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "rule_name": {"type": "string", "description": "Filter by rule name"},
                        "status": {"type": "string", "description": "Filter by status (completed, failed, ignored)"},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            },
            {
                "name": "get_rules",
                "description": "Get configured automation rules",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "enabled_only": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "get_conversation_history",
                "description": "Get recent conversation history",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "integer"},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            },
            {
                "name": "get_person_locations",
                "description": "Get current location of all tracked household members",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_person_sightings",
                "description": "Get recent camera sightings for a specific person",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "person_id": {"type": "string", "description": "Person identifier"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["person_id"],
                },
            },
            {
                "name": "get_person_activities",
                "description": "Get recent detected activities for a person (eating, sleeping, etc.)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "person_id": {"type": "string", "description": "Person identifier"},
                        "activity_type": {"type": "string", "description": "Filter by activity type"},
                        "minutes": {"type": "integer", "description": "Lookback window in minutes", "default": 60},
                    },
                    "required": ["person_id"],
                },
            },
            {
                "name": "get_workflow_executions",
                "description": "Get recent pipeline workflow executions",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "rule_name": {"type": "string", "description": "Filter by rule name"},
                        "status": {"type": "string", "description": "Filter by status (running, waiting, completed, failed)"},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            },
            {
                "name": "get_rule_pipeline",
                "description": "Get the pipeline step definitions for a specific rule",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "rule_id": {"type": "integer", "description": "Rule ID"},
                    },
                    "required": ["rule_id"],
                },
            },
            {
                "name": "trigger_rule",
                "description": "Manually trigger a rule's pipeline execution",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "rule_id": {"type": "integer", "description": "Rule ID to trigger"},
                    },
                    "required": ["rule_id"],
                },
            },
            {
                "name": "get_eink_display_status",
                "description": "Get current e-ink display status (active image, expiry) for one or all displays",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sensor_id": {"type": "string", "description": "Optional sensor ID to filter to a specific display"},
                    },
                },
            },
        ]

        if enabled_tools:
            return [t for t in all_tools if t["name"] in enabled_tools]
        return all_tools
