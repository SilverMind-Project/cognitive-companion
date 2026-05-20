"""
MCP server powered by the official MCP Python SDK.

Defines read-only tools for AI agent integration (Claude Desktop, custom agents)
and exposes them via the MCP protocol (streamable HTTP transport). The same tool
functions are shared with the Gemini Live voice companion via GeminiToolAdapter.
"""

from __future__ import annotations

# Workaround for module name collision: ``backend/mcp/`` shadows the ``mcp``
# PyPI package when ``backend/`` is on sys.path (e.g. during pytest).
# Temporarily strip any path entry whose basename is "backend" so that
# ``import mcp`` resolves to the installed package, not this sub-package.
import os as _os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

_original_path = sys.path.copy()
_collision_paths = [
    p for p in sys.path
    if p == "" or _os.path.basename(p.rstrip("/")) == "backend"
]
for _p in _collision_paths:
    if _p in sys.path:
        sys.path.remove(_p)

try:
    from mcp.server.fastmcp import FastMCP
finally:
    sys.path = _original_path

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.core.config import settings  # noqa: E402
from backend.core.logging import get_logger  # noqa: E402

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
    interactive_response: Any = None
    semantic_memory_client: Any = None
    cts_runtime: Any = None
    ws_manager: Any = None
    knowledge_query: Any = None
    knowledge_delivery: Any = None


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
    interactive_response=None,
    semantic_memory_client=None,
    cts_runtime=None,
    ws_manager=None,
    knowledge_query=None,
    knowledge_delivery=None,
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
    _svc.interactive_response = interactive_response
    _svc.semantic_memory_client = semantic_memory_client
    _svc.cts_runtime = cts_runtime
    _svc.ws_manager = ws_manager
    _svc.knowledge_query = knowledge_query
    _svc.knowledge_delivery = knowledge_delivery


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
                "trigger_types": r.trigger_types,
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
    if not _svc.ha_client or not _svc.ha_client.configured:
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
# Semantic Memory read tools
# ---------------------------------------------------------------------------


@_register
async def get_recent_scene_objects(
    room_id: str,
    minutes: int = 60,
) -> list[dict]:
    """Get recent objects detected in a room from semantic memory.

    Args:
        room_id: Room identifier to query.
        minutes: Lookback window in minutes (default 60).

    Returns:
        List of dicts with label, last_seen_minutes_ago, observation_count.
    """
    client = _svc.semantic_memory_client
    if not client:
        return [{"error": "Semantic memory service not available"}]

    try:
        from backend.integrations.semantic_memory_client import ObjectPresenceRecord

        records = await client.get_recent_objects(room_id, since_minutes=minutes)
        now = datetime.now(UTC)
        results: list[dict] = []
        for rec in records:
            if isinstance(rec, ObjectPresenceRecord):
                delta = (now - rec.last_seen_at).total_seconds() / 60
                results.append(
                    {
                        "label": rec.label,
                        "last_seen_minutes_ago": round(delta, 1),
                        "observation_count": rec.observation_count,
                    }
                )
        return results
    except Exception as exc:
        logger.error("get_recent_scene_objects_error", room_id=room_id, error=str(exc))
        return [{"error": str(exc)}]


@_register
async def get_scene_observations(
    room_id: str | None = None,
    since_minutes: int = 60,
    objects_any: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    """Get recent scene observations from semantic memory.

    Args:
        room_id: Optional room to filter observations.
        since_minutes: Lookback window in minutes (default 60).
        objects_any: Optional list of object labels to filter by.
        limit: Maximum number of observations (default 5).

    Returns:
        List of dicts with id, observed_at, room_name, description,
        object_list, hazard_flags. No raw embeddings.
    """
    client = _svc.semantic_memory_client
    if not client:
        return [{"error": "Semantic memory service not available"}]

    try:
        from backend.integrations.semantic_memory_client import ObservationSearchRequest

        req = ObservationSearchRequest(
            room_id=room_id,
            since_minutes=since_minutes,
            objects_any=objects_any or [],
            limit=limit,
        )
        hits = await client.search_observations(req)
        return [
            {
                "id": hit.id,
                "observed_at": hit.observed_at.isoformat() if hit.observed_at else None,
                "room_id": hit.room_id,
                "description": hit.description,
                "object_list": hit.object_list,
                "hazard_flags": hit.hazard_flags,
            }
            for hit in hits
        ]
    except Exception as exc:
        logger.error("get_scene_observations_error", error=str(exc))
        return [{"error": str(exc)}]


@_register
async def get_person_movements(
    person_id: str,
    semantic: str | None = None,
    minutes: int = 60,
) -> list[dict]:
    """Get recent movement transitions for a person from semantic memory.

    Args:
        person_id: Person identifier.
        semantic: Optional direction semantic filter (entering, exiting, etc.).
        minutes: Lookback window in minutes (default 60).

    Returns:
        List of movement transition dicts.
    """
    client = _svc.semantic_memory_client
    if not client:
        return [{"error": "Semantic memory service not available"}]

    try:
        transitions = await client.get_transitions(
            person_id,
            semantic=semantic,
            since_minutes=minutes,
        )
        return [
            {
                "id": t.id,
                "person_id": t.person_id,
                "from_room_id": t.from_room_id,
                "to_room_id": t.to_room_id,
                "direction_semantic": t.direction_semantic,
                "confidence": t.confidence,
                "observed_at": t.observed_at.isoformat() if t.observed_at else None,
            }
            for t in transitions
        ]
    except Exception as exc:
        logger.error("get_person_movements_error", person_id=person_id, error=str(exc))
        return [{"error": str(exc)}]


@_register
async def get_room_trend(room_id: str) -> dict:
    """Get current room trend data from semantic memory.

    Args:
        room_id: Room identifier.

    Returns:
        Dict with clutter_score, trend_direction, overall_severity,
        persistent_objects, novel_objects, anomalies.
    """
    client = _svc.semantic_memory_client
    if not client:
        return {"error": "Semantic memory service not available"}

    try:
        result = await client.get_room_trends(room_id)
        if result is None:
            return {"room_id": room_id, "trend_direction": "unknown"}
        return {
            "room_id": result.room_id,
            "room_name": result.room_name,
            "clutter_score": result.clutter_score,
            "trend_direction": result.trend_direction,
            "overall_severity": result.overall_severity,
            "persistent_objects": result.persistent_objects,
            "novel_objects": result.novel_objects,
            "anomalies": result.anomalies,
        }
    except Exception as exc:
        logger.error("get_room_trend_error", room_id=room_id, error=str(exc))
        return {"error": str(exc)}


@_register
async def search_similar_scenes(
    query_text: str,
    room_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Search semantic memory for scenes similar to a text query.

    Args:
        query_text: Natural language query (e.g. "person sitting on floor").
        room_id: Optional room to restrict search.
        limit: Maximum results (default 5).

    Returns:
        List of matching observation dicts. Embedding fields are stripped.
    """
    client = _svc.semantic_memory_client
    if not client:
        return [{"error": "Semantic memory service not available"}]

    try:
        from backend.integrations.semantic_memory_client import ObservationSearchRequest

        req = ObservationSearchRequest(
            room_id=room_id,
            query_text=query_text,
            limit=limit,
        )
        hits = await client.search_observations(req)
        # Strip embedding fields even if present upstream
        return [
            {
                "id": hit.id,
                "observed_at": hit.observed_at.isoformat() if hit.observed_at else None,
                "room_id": hit.room_id,
                "description": hit.description,
                "object_list": hit.object_list,
                "hazard_flags": hit.hazard_flags,
                "text_similarity": hit.text_similarity,
                "image_similarity": hit.image_similarity,
                "source": hit.source,
            }
            for hit in hits
        ]
    except Exception as exc:
        logger.error("search_similar_scenes_error", error=str(exc))
        return [{"error": str(exc)}]


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

    # No existing report: generate one on demand

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


# ---------------------------------------------------------------------------
# Interactive Response tool
# ---------------------------------------------------------------------------


@_register
async def submit_user_response(
    execution_id: int,
    step_id: int,
    needs_help: bool,
    user_statement: str | None = None,
) -> dict:
    """Submit the user's response to the system's question about whether they need help.

    Args:
        execution_id: The workflow execution ID.
        step_id: The pipeline step ID.
        needs_help: True if user needs help, False if user is okay.
        user_statement: The user's exact words (optional).

    Returns:
        Success confirmation or error dict.
    """
    # Validate required parameters
    if not isinstance(execution_id, int) or execution_id <= 0:
        return {"error": "execution_id must be a positive integer"}
    if not isinstance(step_id, int) or step_id <= 0:
        return {"error": "step_id must be a positive integer"}
    if not isinstance(needs_help, bool):
        return {"error": "needs_help must be a boolean"}

    # Map needs_help to action
    action = "escalate" if needs_help else "dismiss"

    # Build raw_response_json for audit
    raw_response: dict[str, Any] = {
        "needs_help": needs_help,
    }
    if user_statement:
        raw_response["user_statement"] = user_statement

    # Get InteractiveResponseService from service container
    interactive_response_service = _svc.interactive_response
    if not interactive_response_service:
        return {"error": "Interactive response service not available"}

    # Record the response
    try:
        response = await interactive_response_service.record_response(
            execution_id=execution_id,
            step_id=step_id,
            channel="pwa_realtime_ai",
            action=action,
            timestamp=datetime.now(UTC),
            raw_response=raw_response,
        )

        if response is None:
            # Duplicate response (already recorded)
            return {
                "success": True,
                "message": "Response already recorded (duplicate ignored)",
            }

        # Broadcast to all connected frontend clients so any open popup dialog
        # is dismissed when the user responds via voice.
        if _svc.ws_manager:
            try:
                await _svc.ws_manager.broadcast({
                    "type": "interactive_response",
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "action": action,
                    "channel": "pwa_realtime_ai",
                })
            except Exception as broadcast_err:
                logger.error(
                    "submit_user_response_broadcast_error",
                    execution_id=execution_id,
                    step_id=step_id,
                    error=str(broadcast_err),
                )

        return {
            "success": True,
            "message": f"Response recorded: {action}",
            "action": action,
        }

    except ValueError as e:
        logger.error(
            "submit_user_response_validation_error",
            execution_id=execution_id,
            step_id=step_id,
            error=str(e),
        )
        return {"error": f"Validation error: {e}"}
    except Exception as e:
        logger.error(
            "submit_user_response_error",
            execution_id=execution_id,
            step_id=step_id,
            error=str(e),
        )
        return {"error": f"Failed to record response: {e}"}


# ---------------------------------------------------------------------------
# CTS tracking MCP tools (M9)
# ---------------------------------------------------------------------------


@_register
async def get_tracking_status() -> dict:
    """Return a summary of the continuous-tracking runtime.

    Reports whether CTS is enabled, the consumer_id used, and which
    stream subscribers are currently running. Returns a structured dict
    with ``enabled`` set to ``False`` when the feature flag is off so
    downstream agents can branch cleanly.
    """
    if not settings.get("cts.enabled", False):
        return {"enabled": False, "subscribers": []}

    runtime = _svc.cts_runtime
    if runtime is None:
        return {"enabled": True, "subscribers": [], "error": "runtime_not_started"}
    return {"enabled": True, **runtime.status()}


@_register
async def get_person_location(person_id: str) -> dict:
    """Return the currently inferred room and history for ``person_id``.

    Reads the :class:`PersonLocationState` row and the open
    :class:`PersonLocationHistory` row (if any) so the caller can reason
    about "how long have they been there".
    """
    from backend.models.person import PersonLocationHistory, PersonLocationState

    db: Session = _svc.db_factory()
    try:
        state = (
            db.query(PersonLocationState)
            .filter(PersonLocationState.person_id == person_id)
            .first()
        )
        if state is None:
            return {"person_id": person_id, "found": False}

        latest = (
            db.query(PersonLocationHistory)
            .filter(
                PersonLocationHistory.person_id == person_id,
                PersonLocationHistory.exited_at.is_(None),
                PersonLocationHistory.superseded_by_revision_id.is_(None),
            )
            .order_by(PersonLocationHistory.entered_at.desc())
            .first()
        )

        entered_iso = latest.entered_at.isoformat() if latest and latest.entered_at else None
        dwell_minutes: float | None = None
        if latest and latest.entered_at:
            entered = latest.entered_at
            if entered.tzinfo is None:
                entered = entered.replace(tzinfo=UTC)
            dwell_minutes = round((datetime.now(UTC) - entered).total_seconds() / 60.0, 2)

        return {
            "person_id": person_id,
            "found": True,
            "current_room_name": state.current_room_name,
            "current_room_id": state.current_room_id,
            "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
            "last_sensor_id": state.last_sensor_id,
            "status": state.status,
            "confidence": state.confidence,
            "entered_current_room_at": entered_iso,
            "dwell_minutes": dwell_minutes,
        }
    finally:
        db.close()


@_register
async def get_recent_dementia_signals(
    person_id: str | None = None,
    window_hours: int = 24,
    signal_kind: str | None = None,
    severity_min: str = "info",
    limit: int = 50,
) -> dict:
    """Return recent dementia signals, optionally filtered by person / kind.

    ``severity_min`` accepts ``info``, ``warning``, ``emergency`` and
    returns only signals at that severity or higher.
    """
    from backend.services.cts.signal_store import SignalStore

    order = ["info", "warning", "emergency"]
    try:
        min_idx = order.index(severity_min)
    except ValueError:
        min_idx = 0

    store = SignalStore(db_factory=_svc.db_factory)
    results: list[dict] = []
    for sev in order[min_idx:]:
        batch, _ = await store.list_recent(
            person_id=person_id,
            signal_type=signal_kind,
            severity=sev,
            window_hours=window_hours,
            limit=limit,
        )
        results.extend(batch)
    # Deduplicate by id.
    seen: set[int] = set()
    deduped: list[dict] = []
    for sig in results:
        sid = sig.get("id")
        if isinstance(sid, int):
            if sid in seen:
                continue
            seen.add(sid)
        deduped.append(sig)
    deduped.sort(
        key=lambda s: s.get("received_at") or "",
        reverse=True,
    )
    return {
        "count": len(deduped),
        "window_hours": window_hours,
        "person_id": person_id,
        "signals": deduped[:limit],
    }


@_register
async def query_knowledge_base(query: str) -> dict:
    """Answer factual questions about the senior's life, family, biography,
    medications, preferences, routines, and other STABLE facts that the
    caregiver has documented.

    Use this for: "How many grandchildren do I have?", "What is my
    daughter's name?", "What medication do I take in the morning?".

    Do NOT use for: today's events, current location, recent activity,
    weather, or sensor observations. Use get_person_timeline,
    get_daily_report, get_recent_scene_objects, or get_weather for those.

    Returns {answer, source_documents, found}. When found=False, the
    knowledge base does not have the answer; respond from another tool
    or tell the senior you don't know.
    """
    import time
    t0 = time.monotonic()

    if _svc.knowledge_query is None:
        return {"answer": "", "source_documents": [], "found": False}

    result = await _svc.knowledge_query.answer(query)
    latency_ms = int((time.monotonic() - t0) * 1000)

    # Log the query
    _svc.knowledge_query.log_query(
        result,
        channel="voice",
        latency_ms=latency_ms,
    )

    # Broadcast popup to companion PWA
    if _svc.ws_manager and result.answered_via == "rag":
        await _svc.ws_manager.broadcast({
            "type": "knowledge_answer",
            "query_id": -1,  # filled by log_query return; -1 is ok for ws
            "query_text": result.query_text,
            "answer_text": result.answer_text,
            "source_document_ids": list(result.source_document_ids),
            "server_timestamp": datetime.now(UTC).isoformat(),
        })

    return {
        "answer": result.answer_text,
        "source_documents": list(result.source_document_ids),
        "found": result.answered_via == "rag",
    }


@_register
async def get_current_quiz_question(session_id: int) -> dict:
    """Return the question the senior should answer next in this quiz
    session: its ord, text, type, and choices. Call this before asking
    the senior a question.
    """
    if _svc.knowledge_delivery is None:
        return {"error": "Delivery service not available"}
    return _svc.knowledge_delivery.get_current_question(session_id)


@_register
async def submit_quiz_answer(
    session_id: int,
    question_ord: int,
    choice_id: str | None = None,
    open_ended_text: str | None = None,
) -> dict:
    """Record the senior's answer to the current quiz question. Use exactly
    one of choice_id (multiple choice) or open_ended_text (free-form).
    Always call this after the senior responds; do not skip ahead.
    """
    import time
    t0 = time.monotonic()

    if _svc.knowledge_delivery is None:
        return {"error": "Delivery service not available"}

    latency_ms = int((time.monotonic() - t0) * 1000)
    result = await _svc.knowledge_delivery.submit_quiz_answer(
        session_id=session_id,
        question_ord=question_ord,
        choice_id=choice_id,
        open_ended_text=open_ended_text,
        channel="voice",
        latency_ms=latency_ms,
    )

    return result


@_register
async def complete_quiz_session(session_id: int) -> dict:
    """Finalize a quiz session when the senior says they are done or after
    the last question is answered.
    """
    if _svc.knowledge_delivery is None:
        return {"error": "Delivery service not available"}

    result = await _svc.knowledge_delivery.complete_quiz_session(session_id)
    return result


# ---------------------------------------------------------------------------
# Rule authoring (Phase 7: import/export + plugin metadata for agents)
# ---------------------------------------------------------------------------


@_register
async def list_rules() -> list[dict]:
    """List all rules with summary info (name, description, enabled, trigger_types)."""
    from backend.models.rule import Rule

    db = _svc.db_factory()
    try:
        rules = db.query(Rule).order_by(Rule.name).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "enabled": r.enabled,
                "trigger_types": r.trigger_types,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rules
        ]
    finally:
        db.close()


@_register
async def list_plugin_metadata(
    kind: str | None = None,
) -> list[dict]:
    """Return metadata for every registered plugin (step, filter, or channel).

    Args:
        kind: Filter by kind. One of 'step', 'filter', 'channel'. If None, returns all.
    """
    from backend.channels import ChannelRegistry
    from backend.filters import FilterRegistry
    from backend.steps import StepRegistry

    results: list[dict] = []

    if kind is None or kind == "step":
        StepRegistry.discover()
        for meta in StepRegistry.all_metadata():
            results.append({
                "kind": "step",
                "type_name": meta.type_name,
                "display_name": meta.display_name,
                "category": meta.category,
                "icon": meta.icon,
                "description": meta.description,
                "config_schema": meta.config_schema,
                "default_config": meta.default_config,
                "output_schema": meta.output_schema,
                "schema_version": meta.schema_version,
                "deprecated": meta.deprecated,
                "tags": list(meta.tags),
            })

    if kind is None or kind == "filter":
        FilterRegistry.discover()
        for meta in FilterRegistry.all_metadata():
            results.append({
                "kind": "filter",
                "type_name": meta.filter_type,
                "display_name": meta.display_name,
                "description": meta.description,
                "config_schema": meta.config_schema,
                "schema_version": meta.schema_version,
            })

    if kind is None or kind == "channel":
        ChannelRegistry.discover()
        for meta in ChannelRegistry.all_metadata():
            results.append({
                "kind": "channel",
                "type_name": meta.channel_name,
                "display_name": meta.display_name,
                "description": meta.description,
                "config_schema": meta.config_schema,
                "schema_version": meta.schema_version,
            })

    return results


@_register
async def get_rule_bundle(rule_id: int) -> dict:
    """Export a rule as a portable bundle that can be shared or imported into another install."""
    from importlib.metadata import version as _pkg_version

    from sqlalchemy.orm import joinedload

    from backend.models.rule import Rule
    from backend.services.rule_serializer import rule_to_bundle

    db = _svc.db_factory()
    try:
        rule = (
            db.query(Rule)
            .options(
                joinedload(Rule.steps),
                joinedload(Rule.contexts),
                joinedload(Rule.dependencies),
                joinedload(Rule.cron_triggers),
            )
            .filter(Rule.id == rule_id)
            .first()
        )
        if not rule:
            return {"error": f"Rule {rule_id} not found"}

        bundle = rule_to_bundle(rule, app_version=_pkg_version("cognitive-companion"))
        return bundle.model_dump(mode="json")
    finally:
        db.close()


@_register
async def import_rule_bundle(
    bundle: dict,
    mode: str = "preview",
) -> dict:
    """Validate and optionally commit a rule bundle. Returns the same report the UI shows.

    Args:
        bundle: The RuleBundle as a JSON dict.
        mode: 'preview' validates without writing; 'commit' writes to the database.
    """
    from importlib.metadata import version as _pkg_version

    from backend.schemas.rule_bundle import RuleBundle
    from backend.services.rule_serializer import validate_bundle

    app_version = _pkg_version("cognitive-companion")

    try:
        parsed = RuleBundle(**bundle)
    except Exception as e:
        return {"status": "error", "errors": [f"Invalid bundle: {e}"]}

    if mode == "preview":
        return validate_bundle(parsed, app_version).model_dump(mode="json")

    # Commit mode
    db = _svc.db_factory()
    try:
        from backend.models.cron_trigger import CronTrigger
        from backend.models.pipeline import PipelineStep
        from backend.models.rule import Rule, RuleContext, RuleDependency

        # Validate first
        report = validate_bundle(parsed, app_version)
        if report.status == "error":
            return report.model_dump(mode="json")

        existing = db.query(Rule).filter(Rule.name == parsed.rule.name).first()
        if existing:
            return {"status": "error", "errors": [f"Rule '{parsed.rule.name}' already exists"]}

        rule_def = parsed.rule
        rule = Rule(
            name=rule_def.name,
            description=rule_def.description,
            enabled=rule_def.enabled,
            trigger_types=rule_def.trigger_types,
            primary_sensor_id=rule_def.primary_sensor_ref.label
            if rule_def.primary_sensor_ref
            else None,
            cool_off_minutes=rule_def.cool_off_minutes,
            max_daily_triggers=rule_def.max_daily_triggers,
            max_concurrent_executions=rule_def.max_concurrent_executions,
            execution_timeout_minutes=rule_def.execution_timeout_minutes,
            webhook_config=rule_def.webhook_config,
            occupancy_config=rule_def.occupancy_config,
            telegram_trigger_config=rule_def.telegram_trigger_config,
        )
        db.add(rule)
        db.flush()

        for ce in rule_def.cron_expressions:
            ct = CronTrigger(
                name=f"{rule_def.name} ({ce.expression})",
                expression=ce.expression,
                timezone=ce.timezone,
            )
            db.add(ct)
            db.flush()
            rule.cron_triggers.append(ct)

        for ctx_bundle in parsed.contexts:
            ctx = RuleContext(
                rule_id=rule.id,
                context_type=ctx_bundle.context_type,
                config_json=ctx_bundle.config,
                negate=ctx_bundle.negate,
            )
            db.add(ctx)

        step_id_map: dict[str, int] = {}
        for i, step_bundle in enumerate(parsed.steps):
            step = PipelineStep(
                rule_id=rule.id,
                order=i,
                step_type=step_bundle.step_type,
                label=step_bundle.label,
                config_json=step_bundle.config,
                enabled=step_bundle.enabled,
            )
            db.add(step)
            db.flush()
            step_id_map[step_bundle.label] = step.id

        for step_bundle in parsed.steps:
            step_id = step_id_map[step_bundle.label]
            step = db.get(PipelineStep, step_id)
            if step and step_bundle.branches.on_true:
                step.next_step_on_true = step_id_map.get(step_bundle.branches.on_true)
            if step and step_bundle.branches.on_false:
                step.next_step_on_false = step_id_map.get(step_bundle.branches.on_false)

        for dep_bundle in parsed.dependencies:
            parent = db.query(Rule).filter(Rule.name == dep_bundle.parent_rule_name).first()
            if parent:
                dep = RuleDependency(
                    dependent_rule_id=rule.id,
                    parent_rule_id=parent.id,
                    lookback_minutes=dep_bundle.lookback_minutes,
                    require_success=dep_bundle.require_success,
                )
                db.add(dep)

        db.commit()
        report.rule_id = rule.id
        report.status = "ok"
        return report.model_dump(mode="json")
    except Exception as e:
        db.rollback()
        return {"status": "error", "errors": [str(e)]}
    finally:
        db.close()
