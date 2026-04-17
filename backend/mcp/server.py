"""
MCP server powered by the official MCP Python SDK.

Defines read-only tools for AI agent integration (Claude Desktop, custom agents)
and exposes them via the MCP protocol (streamable HTTP transport). The same tool
functions are shared with the Gemini Live voice companion via GeminiToolAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Service container (populated once during FastAPI lifespan via init_services)
# ---------------------------------------------------------------------------


@dataclass
class MCPServices:
    """Holds shared service references for MCP tool functions."""

    db_factory: Any = None
    event_aggregator: Any = None
    sensor_polling: Any = None
    ha_client: Any = None
    person_tracking: Any = None
    activity_timeline: Any = None
    activity_session: Any = None
    daily_report: Any = None


_svc = MCPServices()


def init_services(
    db_session_factory,
    event_aggregator=None,
    sensor_polling_service=None,
    ha_client=None,
    person_tracking=None,
    activity_timeline=None,
    activity_session=None,
    daily_report=None,
) -> None:
    """Populate the module-level service container. Called once from lifespan."""
    _svc.db_factory = db_session_factory
    _svc.event_aggregator = event_aggregator
    _svc.sensor_polling = sensor_polling_service
    _svc.ha_client = ha_client
    _svc.person_tracking = person_tracking
    _svc.activity_timeline = activity_timeline
    _svc.activity_session = activity_session
    _svc.daily_report = daily_report


# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp_server = FastMCP("cognitive-companion")

# Parallel registry for direct invocation (used by GeminiToolAdapter)
_tool_handlers: dict[str, Any] = {}


def _register(fn):
    """Register a function as both an MCP tool and a direct-call handler."""
    _tool_handlers[fn.__name__] = fn
    return mcp_server.tool()(fn)


def get_tool_registry() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (handler_dict, schema_list) for the Gemini adapter.

    Schemas are extracted from the FastMCP internal tool manager and converted
    to plain dicts with ``name``, ``description``, and ``inputSchema`` keys.
    """
    schemas: list[dict[str, Any]] = []
    for tool in mcp_server._tool_manager._tools.values():
        schema: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description or "",
        }
        if tool.parameters:
            schema["inputSchema"] = tool.parameters
        schemas.append(schema)
    return _tool_handlers, schemas


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@_register
async def get_rooms() -> list[dict]:
    """Get all rooms configured in the system."""
    from backend.models.room import Room

    db: Session = _svc.db_factory()
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


@_register
async def get_sensors(room_name: str | None = None, sensor_type: str | None = None) -> list[dict]:
    """Get sensors, optionally filtered by room name or sensor type."""
    from backend.models.sensor import Sensor

    db: Session = _svc.db_factory()
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
            result.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "room": room,
                    "sensor_type": s.sensor_type,
                    "source": s.source,
                    "enabled": s.enabled,
                }
            )
        return result
    finally:
        db.close()


@_register
async def get_room_occupancy(room_name: str | None = None) -> dict:
    """Get current room occupancy status from presence sensors."""
    if _svc.sensor_polling:
        summary = await _svc.sensor_polling.get_occupancy_summary()
        if room_name:
            return {
                k: v for k, v in summary.items() if v.get("room", "").lower() == room_name.lower()
            }
        return summary
    return {"message": "Sensor polling not available"}


@_register
async def get_recent_images(sensor_id: str, limit: int = 5) -> list[str]:
    """Get recent images from a camera sensor."""
    if _svc.event_aggregator:
        return await _svc.event_aggregator.get_recent_images(sensor_id, limit=limit)
    return []


@_register
async def get_light_level(entity_id: str) -> dict:
    """Get current light level (illuminance) from a Home Assistant sensor."""
    if _svc.ha_client:
        level = await _svc.ha_client.get_light_level(entity_id)
        return {"entity_id": entity_id, "illuminance_lux": level}
    return {"error": "Home Assistant not configured"}


@_register
async def get_alerts(
    resolved: bool | None = None,
    room_name: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Get recent emergency alerts, optionally filtered by resolved state or room."""
    from backend.models.alert import EmergencyAlert

    db: Session = _svc.db_factory()
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


@_register
async def get_event_logs(
    rule_name: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Get recent rule execution event logs."""
    from backend.models.event import EventLog

    db: Session = _svc.db_factory()
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


@_register
async def get_rules(enabled_only: bool = True) -> list[dict]:
    """Get configured automation rules."""
    from backend.models.rule import Rule

    db: Session = _svc.db_factory()
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


@_register
async def get_conversation_history(session_id: int | None = None, limit: int = 20) -> list[dict]:
    """Get recent conversation turns (placeholder)."""
    return [{"message": "Use /api/v1/conversations endpoint for history"}]


@_register
async def get_person_locations() -> list[dict]:
    """Get current location of all tracked household members."""
    if _svc.person_tracking:
        return await _svc.person_tracking.get_person_locations()
    return [{"message": "Person tracking not available"}]


@_register
async def get_enrolled_persons() -> list[dict]:
    """Get list of household members with face identification enrollment data."""
    from backend.models.person import HouseholdMember

    db: Session = _svc.db_factory()
    try:
        members = db.execute(select(HouseholdMember)).scalars().all()
        return [
            {
                "id": m.id,
                "name": m.name,
                "is_guest": m.is_guest,
            }
            for m in members
        ]
    finally:
        db.close()


@_register
async def get_person_sightings(person_id: str, limit: int = 10) -> list[dict]:
    """Get recent camera sightings for a specific person."""
    if _svc.person_tracking:
        return await _svc.person_tracking.get_recent_sightings(person_id, limit=limit)
    return [{"message": "Person tracking not available"}]


@_register
async def get_person_activities(
    person_id: str,
    activity_type: str | None = None,
    minutes: int = 60,
) -> list[dict]:
    """Get recent detected activities for a person (eating, sleeping, etc.)."""
    if _svc.person_tracking:
        return await _svc.person_tracking.get_recent_activities(
            person_id, activity_type=activity_type, minutes=minutes
        )
    return [{"message": "Person tracking not available"}]


@_register
async def get_workflow_executions(
    rule_name: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Get recent pipeline workflow executions."""
    from backend.models.pipeline import WorkflowExecution
    from backend.models.rule import Rule

    db: Session = _svc.db_factory()
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
            results.append(
                {
                    "id": ex.id,
                    "rule_id": ex.rule_id,
                    "rule_name": rule.name if rule else None,
                    "status": ex.status,
                    "started_at": ex.started_at.isoformat() if ex.started_at else None,
                    "updated_at": ex.updated_at.isoformat() if ex.updated_at else None,
                    "error": ex.error,
                }
            )
        return results
    finally:
        db.close()


@_register
async def get_rule_pipeline(rule_id: int) -> list[dict]:
    """Get pipeline step definitions for a specific rule."""
    from backend.models.pipeline import PipelineStep

    db: Session = _svc.db_factory()
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


@_register
async def trigger_rule(rule_id: int) -> dict:
    """Manually trigger a rule's pipeline execution."""
    try:
        from backend.services.pipeline_executor import TriggerContext
        from backend.services.scheduler import _pipeline_executor

        if not _pipeline_executor:
            return {"error": "Pipeline executor not available"}

        from backend.models.rule import Rule

        db: Session = _svc.db_factory()
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


@_register
async def get_eink_display_status(sensor_id: str | None = None) -> list[dict]:
    """Get current e-ink display status (active image, expiry) for one or all displays."""
    from backend.models.image_state import ActiveImageState

    db: Session = _svc.db_factory()
    try:
        stmt = select(ActiveImageState)
        if sensor_id:
            stmt = stmt.where(ActiveImageState.sensor_id == sensor_id)
        states = db.execute(stmt).scalars().all()
        now = datetime.now(UTC)
        results: list[dict] = []
        for state in states:
            results.append(
                {
                    "sensor_id": state.sensor_id,
                    "has_active_image": True,
                    "expired": bool(state.expires_at and state.expires_at < now),
                    "expires_at": state.expires_at.isoformat() if state.expires_at else None,
                    "rendered_text": state.rendered_text,
                }
            )
        return results
    finally:
        db.close()


# ---------------------------------------------------------------------------
# New tools
# ---------------------------------------------------------------------------


@_register
async def get_local_datetime() -> dict:
    """Get the current local date and time for the household's timezone."""
    tz_name = settings.get("app.timezone", "America/New_York")
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "day_of_week": now.strftime("%A"),
        "timezone": tz_name,
    }


@_register
async def get_weather() -> dict:
    """Get the current weather from Home Assistant."""
    if not _svc.ha_client or not getattr(_svc.ha_client, "configured", False):
        return {"error": "Home Assistant not configured"}
    try:
        state = await _svc.ha_client.get_entity_state("weather.forecast_home")
        if not state:
            return {"error": "Weather entity not available"}
        attrs = state.get("attributes", {})
        return {
            "state": state.get("state"),
            "temperature": attrs.get("temperature"),
            "temperature_unit": attrs.get("temperature_unit"),
            "humidity": attrs.get("humidity"),
            "wind_speed": attrs.get("wind_speed"),
            "wind_speed_unit": attrs.get("wind_speed_unit"),
            "forecast": attrs.get("forecast", [])[:3],
        }
    except Exception as exc:
        logger.error("get_weather_error", error=str(exc))
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Timeline, Reports, Sessions tools
# ---------------------------------------------------------------------------


@_register
async def get_person_timeline(
    person_id: str,
    minutes: int = 60,
) -> list[dict]:
    """Get the unified activity timeline for a person over a time window."""
    if not _svc.activity_timeline:
        return [{"error": "Timeline service not available"}]

    from datetime import UTC, timedelta

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(minutes=minutes)
    events = _svc.activity_timeline.get_timeline(
        person_id=person_id,
        start_time=start_time,
        end_time=end_time,
        limit=200,
    )
    return events


@_register
async def get_daily_report(
    person_id: str,
    date: str,
) -> dict:
    """Get or generate a daily report for a person on a specific date.

    Args:
        person_id: Household member ID.
        date: Date in YYYY-MM-DD format.

    Returns:
        Daily report dict with aggregated metrics.
    """
    if not _svc.daily_report:
        return {"error": "Daily report service not available"}

    report = _svc.daily_report.get_report(person_id=person_id, date=date)
    if report:
        return report

    # No existing report — generate one on demand

    from backend.core.config import settings

    tz_name = settings.get("app.timezone", "UTC")
    report = _svc.daily_report.generate_daily_report(
        person_id=person_id,
        date=date,
        tz_name=tz_name,
    )
    return report


@_register
async def get_open_sessions(
    person_id: str | None = None,
) -> list[dict]:
    """Get currently open activity sessions.

    Args:
        person_id: Optional household member ID to filter sessions.

    Returns:
        List of open session dicts with activity type, room, and open time.
    """
    if not _svc.activity_session:
        return [{"error": "Activity session service not available"}]

    return _svc.activity_session.get_open_sessions(person_id=person_id)
