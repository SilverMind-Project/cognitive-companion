"""U2-T2: MCP tool registry smoke gate.

Every @_register tool is present and the registry count is asserted so
a tool cannot silently disappear (acceptance criterion 2: MCP stays callable
by openclaw and other AI systems after all U-series changes).
"""

from __future__ import annotations

from backend.mcp.server import _tool_handlers, get_tool_registry

# ---------------------------------------------------------------------------
# Expected tool names — update this set only when a tool is intentionally
# added or removed; the count assertion below will catch accidental removals.
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "get_rooms",
    "get_sensors",
    "get_room_occupancy",
    "get_recent_images",
    "get_light_level",
    "get_signals_feed",
    "get_event_logs",
    "get_rules",
    "get_conversation_history",
    "get_person_locations",
    "get_enrolled_persons",
    "get_person_activities",
    "get_workflow_executions",
    "get_rule_pipeline",
    "trigger_rule",
    "get_eink_display_status",
    "get_local_datetime",
    "get_weather",
    "get_recent_scene_objects",
    "get_scene_observations",
    "get_person_movements",
    "get_room_trend",
    "search_similar_scenes",
    "get_person_timeline",
    "get_daily_report",
    "get_open_sessions",
    "submit_user_response",
    "get_tracking_status",
    "get_person_location",
    "get_recent_dementia_signals",
    "query_knowledge_base",
    "get_current_quiz_question",
    "submit_quiz_answer",
    "complete_quiz_session",
    "get_active_guided_step",
    "mark_guided_step_complete",
    "repeat_guided_step",
    "report_step_blocked",
    "request_caregiver_help",
    "get_guided_completion_summary",
    "get_guided_attempts_per_step",
    "get_guided_time_to_complete",
    "get_guided_abandonment",
    "get_guided_escalation_breakdown",
    "get_guided_vision_agreement",
    "get_guided_watch_summary",
    "get_guided_gate_cost_summary",
    "get_guided_time_of_day",
    "list_rules",
    "list_plugin_metadata",
    "get_rule_bundle",
    "import_rule_bundle",
    "get_heatmap",
    "get_identity_correction_job",
    "get_gait_trend",
    "acknowledge_dementia_signal",
    "list_keyframe_frames",
    "propose_identity_correction",
}

EXPECTED_COUNT = 58


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


def test_tool_count():
    """Exactly EXPECTED_COUNT tools are registered. Update EXPECTED_TOOLS when intentionally changing."""
    actual = set(_tool_handlers.keys())
    assert len(actual) == EXPECTED_COUNT, (
        f"MCP tool count changed: expected {EXPECTED_COUNT}, got {len(actual)}. "
        f"Missing: {EXPECTED_TOOLS - actual}. "
        f"Extra: {actual - EXPECTED_TOOLS}."
    )


def test_all_expected_tools_present():
    """Every expected tool name is in the registry."""
    actual = set(_tool_handlers.keys())
    missing = EXPECTED_TOOLS - actual
    assert not missing, f"Tools missing from registry: {missing}"


def test_no_unexpected_tools():
    """No tool is registered without being in the expected set (prevents silent additions)."""
    actual = set(_tool_handlers.keys())
    unexpected = actual - EXPECTED_TOOLS
    assert not unexpected, f"Unexpected tools registered: {unexpected}"


def test_all_tools_are_callable():
    """Every registered tool handler is an async callable."""
    import inspect

    for name, fn in _tool_handlers.items():
        assert callable(fn), f"Tool {name} is not callable"
        assert inspect.iscoroutinefunction(fn), f"Tool {name} is not async"


def test_get_tool_registry_returns_schemas():
    """get_tool_registry returns (handler_dict, schema_list) with non-empty schemas."""
    handlers, schemas = get_tool_registry()
    assert isinstance(handlers, dict)
    assert isinstance(schemas, list)
    assert len(schemas) == EXPECTED_COUNT, (
        f"Schema list length {len(schemas)} != tool count {EXPECTED_COUNT}"
    )
    for s in schemas:
        assert "name" in s
        assert "description" in s


def test_handler_dict_matches_tool_registry():
    """handler dict and tool registry are in sync."""
    handlers, schemas = get_tool_registry()
    handler_names = set(handlers.keys())
    schema_names = {s["name"] for s in schemas}
    assert handler_names == schema_names, (
        f"Handler/schema mismatch. In handlers only: {handler_names - schema_names}. "
        f"In schemas only: {schema_names - handler_names}."
    )
