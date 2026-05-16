"""Tests for pipeline_data_manager helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.services.pipeline_data_manager import (
    apply_interactive_response,
    apply_step_result,
    build_initial_pipeline_data,
    copy_pipeline_snapshot,
    reserved_pipeline_keys,
    resolve_pipeline_value,
)

# ---------------------------------------------------------------------------
# build_initial_pipeline_data
# ---------------------------------------------------------------------------


def _now_utc():
    return datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)


def _now_local():
    from zoneinfo import ZoneInfo
    return datetime(2024, 1, 15, 7, 0, 0, tzinfo=ZoneInfo("America/New_York"))


def test_build_initial_has_trigger_keys():
    data = build_initial_pipeline_data(
        trigger_type="sensor_event",
        sensor_id="cam1",
        room_name="Kitchen",
        media_paths=["/img/a.jpg"],
        media_type="image",
        webhook_payload=None,
        now_utc=_now_utc(),
        now_local=_now_local(),
        timezone_name="America/New_York",
    )
    assert data["trigger"]["type"] == "sensor_event"
    assert data["trigger"]["sensor_id"] == "cam1"
    assert data["trigger"]["room_name"] == "Kitchen"
    assert data["trigger"]["media_paths"] == ["/img/a.jpg"]


def test_build_initial_has_system_keys():
    data = build_initial_pipeline_data(
        trigger_type="cron",
        sensor_id=None,
        room_name=None,
        media_paths=[],
        media_type="image",
        webhook_payload=None,
        now_utc=_now_utc(),
        now_local=_now_local(),
        timezone_name="America/New_York",
    )
    assert "local_time" in data["system"]
    assert "local_date" in data["system"]
    assert "local_day_of_week" in data["system"]
    assert data["system"]["timezone"] == "America/New_York"


def test_build_initial_system_vars_full_format_set():
    """Verify all date/time template variables are present and correctly formatted.

    Local time fixture is 2024-01-15 07:00 America/New_York (Monday in January,
    odd day 15 → ordinal '15th').
    """
    data = build_initial_pipeline_data(
        trigger_type="cron",
        sensor_id=None,
        room_name=None,
        media_paths=[],
        media_type="image",
        webhook_payload=None,
        now_utc=_now_utc(),
        now_local=_now_local(),
        timezone_name="America/New_York",
    )
    sys = data["system"]
    # Time formats.
    assert sys["local_time"] == "7:00 AM"
    assert sys["local_time_24h"] == "07:00"
    assert sys["local_hour_12h"] == "7"
    assert sys["local_hour_24h"] == "07"
    assert sys["local_minute"] == "00"
    assert sys["local_ampm"] == "AM"
    # Day / date components.
    assert sys["local_date"] == "2024-01-15"
    assert sys["local_day_of_week"] == "Monday"
    assert sys["local_day_of_week_short"] == "Mon"
    assert sys["local_day_of_month"] == 15
    assert sys["local_day_ordinal"] == "15th"
    assert sys["local_month_name"] == "January"
    assert sys["local_month_name_short"] == "Jan"
    assert sys["local_month_number"] == 1
    assert sys["local_year"] == 2024
    # Friendly composites.
    assert sys["local_date_long"] == "January 15th, 2024"
    assert sys["local_date_friendly"] == "Monday, January 15th"


def test_build_initial_system_ordinal_suffix_variants():
    """Spot-check ordinal suffix rules: 1st/2nd/3rd/11th-13th/4th-20th/21st-23rd/24th-30th."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("UTC")
    cases = {
        1: "1st", 2: "2nd", 3: "3rd", 4: "4th",
        11: "11th", 12: "12th", 13: "13th",
        21: "21st", 22: "22nd", 23: "23rd",
        31: "31st",
    }
    for day, expected in cases.items():
        data = build_initial_pipeline_data(
            trigger_type="cron",
            sensor_id=None, room_name=None,
            media_paths=[], media_type="image", webhook_payload=None,
            now_utc=_now_utc(),
            now_local=datetime(2024, 1, day, 12, 0, 0, tzinfo=tz),
            timezone_name="UTC",
        )
        assert data["system"]["local_day_ordinal"] == expected, f"day={day}"


def test_build_initial_has_pipeline_block():
    data = build_initial_pipeline_data(
        trigger_type="manual",
        sensor_id=None,
        room_name=None,
        media_paths=[],
        media_type="image",
        webhook_payload=None,
        now_utc=_now_utc(),
        now_local=_now_local(),
        timezone_name="UTC",
    )
    assert "_pipeline" in data
    assert data["_pipeline"]["completed_at"] is None
    assert "started_at" in data["_pipeline"]


def test_build_initial_has_steps_namespace():
    data = build_initial_pipeline_data(
        trigger_type="manual",
        sensor_id=None,
        room_name=None,
        media_paths=[],
        media_type="image",
        webhook_payload=None,
        now_utc=_now_utc(),
        now_local=_now_local(),
        timezone_name="UTC",
    )
    assert "steps" in data
    assert data["steps"] == {}


def test_build_initial_webhook_payload_injected():
    payload = {"command": "/test", "chat_id": 123}
    data = build_initial_pipeline_data(
        trigger_type="webhook",
        sensor_id=None,
        room_name=None,
        media_paths=[],
        media_type="image",
        webhook_payload=payload,
        now_utc=_now_utc(),
        now_local=_now_local(),
        timezone_name="UTC",
    )
    assert data["trigger_input"] == payload


def test_build_initial_no_webhook_no_trigger_input():
    data = build_initial_pipeline_data(
        trigger_type="sensor_event",
        sensor_id="cam1",
        room_name=None,
        media_paths=[],
        media_type="image",
        webhook_payload=None,
        now_utc=_now_utc(),
        now_local=_now_local(),
        timezone_name="UTC",
    )
    assert "trigger_input" not in data


# ---------------------------------------------------------------------------
# apply_step_result
# ---------------------------------------------------------------------------


def _empty_data() -> dict:
    return {
        "trigger": {},
        "system": {},
        "_pipeline": {"started_at": "x", "completed_at": None},
        "_step_timings": [],
        "steps": {},
    }


def test_apply_step_result_writes_label_key():
    data = _empty_data()
    apply_step_result(data, step_id=12, step_type="llm_call", label="llm_call_1", result_data={"llm_response": "hello"})

    assert "llm_call_1" in data["steps"]
    entry = data["steps"]["llm_call_1"]
    assert entry["step_id"] == 12
    assert entry["step_type"] == "llm_call"
    assert entry["outputs"]["llm_response"] == "hello"


def test_apply_step_result_two_steps_both_survive():
    data = _empty_data()
    apply_step_result(data, step_id=10, step_type="llm_call", label="llm_call_1", result_data={"llm_response": "first"})
    apply_step_result(data, step_id=11, step_type="llm_call", label="llm_call_2", result_data={"llm_response": "second"})

    assert data["steps"]["llm_call_1"]["outputs"]["llm_response"] == "first"
    assert data["steps"]["llm_call_2"]["outputs"]["llm_response"] == "second"


def test_apply_step_result_outputs_deep_copied():
    data = _empty_data()
    result_data = {"nested": {"value": 1}}
    apply_step_result(data, step_id=1, step_type="llm_call", label="llm_call_1", result_data=result_data)

    result_data["nested"]["value"] = 999
    assert data["steps"]["llm_call_1"]["outputs"]["nested"]["value"] == 1


def test_apply_step_result_no_top_level_aliases():
    data = _empty_data()
    apply_step_result(data, step_id=1, step_type="llm_call", label="llm_call_1", result_data={"llm_response": "hello"})

    assert "llm_response" not in data


def test_apply_step_result_cooloff_promoted_to_top_level():
    data = _empty_data()
    apply_step_result(data, step_id=1, step_type="condition", label="condition_1", result_data={"_cooloff_triggered": True})

    assert data.get("_cooloff_triggered") is True
    assert data["steps"]["condition_1"]["outputs"]["_cooloff_triggered"] is True


def test_apply_step_result_cooloff_not_promoted_when_absent():
    data = _empty_data()
    apply_step_result(data, step_id=1, step_type="llm_call", label="llm_call_1", result_data={"llm_response": "x"})

    assert "_cooloff_triggered" not in data


def test_apply_step_result_overwrite_same_label():
    data = _empty_data()
    apply_step_result(data, step_id=5, step_type="llm_call", label="llm_call_1", result_data={"x": 1})
    apply_step_result(data, step_id=5, step_type="llm_call", label="llm_call_1", result_data={"x": 2})

    assert data["steps"]["llm_call_1"]["outputs"]["x"] == 2


# ---------------------------------------------------------------------------
# apply_interactive_response
# ---------------------------------------------------------------------------


def test_apply_interactive_response_writes_output_key():
    data = _empty_data()
    payload = {"channel": "pwa_popup_text", "action": "escalate", "timestamp": "2024-01-01T00:00:00", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label="interactive_prompt_1",
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=False,
        channel="pwa_popup_text",
        action="escalate",
    )

    assert data["steps"]["interactive_prompt_1"]["outputs"]["interactive_response"] == payload
    assert "interactive_prompt_1" in data["steps"]


def test_apply_interactive_response_auto_escalate_on_escalate():
    data = _empty_data()
    payload = {"channel": "pwa_popup_text", "action": "escalate", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label="interactive_prompt_1",
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=True,
        channel="pwa_popup_text",
        action="escalate",
    )

    assert data["steps"]["interactive_prompt_1"]["outputs"].get("auto_escalate_triggered") is True


def test_apply_interactive_response_auto_escalate_on_timeout():
    data = _empty_data()
    payload = {"channel": "timeout", "action": "escalate", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label="interactive_prompt_1",
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=True,
        channel="timeout",
        action="escalate",
    )

    assert data["steps"]["interactive_prompt_1"]["outputs"].get("auto_escalate_triggered") is True


def test_apply_interactive_response_no_auto_escalate_on_dismiss():
    data = _empty_data()
    payload = {"channel": "pwa_popup_text", "action": "dismiss", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label="interactive_prompt_1",
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=True,
        channel="pwa_popup_text",
        action="dismiss",
    )

    assert "auto_escalate_triggered" not in data["steps"]["interactive_prompt_1"]["outputs"]


def test_apply_interactive_response_auto_escalate_disabled():
    data = _empty_data()
    payload = {"channel": "pwa_popup_text", "action": "escalate", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label="interactive_prompt_1",
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=False,
        channel="pwa_popup_text",
        action="escalate",
    )

    assert "auto_escalate_triggered" not in data["steps"]["interactive_prompt_1"]["outputs"]


# ---------------------------------------------------------------------------
# copy_pipeline_snapshot
# ---------------------------------------------------------------------------


def test_copy_pipeline_snapshot_deep_copies():
    data = {"nested": {"value": 1}, "steps": {"llm_call_1": {"outputs": {"x": 2}}}}
    snapshot = copy_pipeline_snapshot(data)

    data["nested"]["value"] = 999
    data["steps"]["llm_call_1"]["outputs"]["x"] = 999

    assert snapshot["nested"]["value"] == 1
    assert snapshot["steps"]["llm_call_1"]["outputs"]["x"] == 2


def test_copy_pipeline_snapshot_is_independent():
    data = {"a": [1, 2, 3]}
    snapshot = copy_pipeline_snapshot(data)
    data["a"].append(4)

    assert snapshot["a"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# resolve_pipeline_value
# ---------------------------------------------------------------------------


def test_resolve_pipeline_value_top_level():
    data = {"trigger": {"type": "sensor_event"}}
    assert resolve_pipeline_value(data, "trigger.type") == "sensor_event"


def test_resolve_pipeline_value_dotted_path():
    data = {"steps": {"llm_call_1": {"outputs": {"llm_response": {"summary": "ok"}}}}}
    result = resolve_pipeline_value(data, "steps.llm_call_1.outputs.llm_response.summary")
    assert result == "ok"


def test_resolve_pipeline_value_missing_returns_default():
    data = {"a": 1}
    assert resolve_pipeline_value(data, "b.c.d", default="fallback") == "fallback"


def test_resolve_pipeline_value_none_default():
    data = {}
    assert resolve_pipeline_value(data, "missing") is None


def test_resolve_pipeline_value_list_index():
    data = {"items": [{"name": "Alice"}, {"name": "Bob"}]}
    assert resolve_pipeline_value(data, "items.0.name") == "Alice"
    assert resolve_pipeline_value(data, "items.1.name") == "Bob"


# ---------------------------------------------------------------------------
# reserved_pipeline_keys
# ---------------------------------------------------------------------------


def test_reserved_pipeline_keys_contains_expected():
    keys = reserved_pipeline_keys()
    for expected in ("trigger", "system", "_pipeline", "_step_timings", "steps", "error"):
        assert expected in keys
