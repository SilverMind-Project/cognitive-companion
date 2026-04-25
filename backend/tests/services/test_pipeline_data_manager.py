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
    slugify_step_label,
)

# ---------------------------------------------------------------------------
# slugify_step_label
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert slugify_step_label("Vision Step") == "vision_step"


def test_slugify_special_chars():
    assert slugify_step_label("My LLM-Call!") == "my_llm_call"


def test_slugify_none():
    assert slugify_step_label(None) is None


def test_slugify_empty():
    assert slugify_step_label("") is None


def test_slugify_whitespace_only():
    assert slugify_step_label("   ") is None


def test_slugify_already_slug():
    assert slugify_step_label("my_step") == "my_step"


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
    assert "by_id" in data["steps"]
    assert "by_label" in data["steps"]
    assert "sequence" in data["steps"]


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
        "steps": {"by_id": {}, "by_label": {}, "sequence": []},
    }


def test_apply_step_result_writes_canonical_namespace():
    data = _empty_data()
    apply_step_result(data, step_id=12, step_type="llm_call", label="Vision Step", result_data={"vision_response": "hello"})

    assert "12" in data["steps"]["by_id"]
    entry = data["steps"]["by_id"]["12"]
    assert entry["step_id"] == 12
    assert entry["step_type"] == "llm_call"
    assert entry["label"] == "Vision Step"
    assert entry["label_slug"] == "vision_step"
    assert entry["outputs"]["vision_response"] == "hello"


def test_apply_step_result_updates_sequence():
    data = _empty_data()
    apply_step_result(data, step_id=1, step_type="llm_call", label=None, result_data={"a": 1})
    apply_step_result(data, step_id=2, step_type="notification", label=None, result_data={"b": 2})

    assert data["steps"]["sequence"] == ["1", "2"]


def test_apply_step_result_sequence_no_duplicates():
    data = _empty_data()
    apply_step_result(data, step_id=5, step_type="llm_call", label=None, result_data={"x": 1})
    apply_step_result(data, step_id=5, step_type="llm_call", label=None, result_data={"x": 2})

    assert data["steps"]["sequence"].count("5") == 1


def test_apply_step_result_two_same_type_both_survive():
    data = _empty_data()
    apply_step_result(data, step_id=10, step_type="llm_call", label="Step A", result_data={"llm_response": "first"})
    apply_step_result(data, step_id=11, step_type="llm_call", label="Step B", result_data={"llm_response": "second"})

    # Both canonical entries survive
    assert data["steps"]["by_id"]["10"]["outputs"]["llm_response"] == "first"
    assert data["steps"]["by_id"]["11"]["outputs"]["llm_response"] == "second"


def test_apply_step_result_label_slug_alias_created():
    data = _empty_data()
    apply_step_result(data, step_id=7, step_type="llm_call", label="My Vision", result_data={"vision_response": "x"})

    assert data["steps"]["by_label"]["my_vision"] == "7"


def test_apply_step_result_reserved_label_not_overwritten():
    data = _empty_data()
    # "trigger" is a reserved key -- slug should not overwrite it
    apply_step_result(data, step_id=3, step_type="llm_call", label="trigger", result_data={"foo": "bar"})

    # The reserved key "trigger" must remain the original dict, not the step output
    assert isinstance(data["trigger"], dict)
    # The label slug "trigger" must not appear in by_label (it's reserved)
    assert "trigger" not in data["steps"]["by_label"]


def test_apply_step_result_legacy_top_level_alias_written():
    data = _empty_data()
    apply_step_result(data, step_id=1, step_type="llm_call", label=None, result_data={"vision_response": "hello"})

    assert data["vision_response"] == "hello"


def test_apply_step_result_alias_collision_recorded():
    data = _empty_data()
    apply_step_result(data, step_id=1, step_type="llm_call", label=None, result_data={"llm_response": "first"})
    apply_step_result(data, step_id=2, step_type="llm_call", label=None, result_data={"llm_response": "second"})

    # Last writer wins at top level
    assert data["llm_response"] == "second"
    # Collision recorded
    collisions = data.get("_alias_collisions", [])
    assert len(collisions) == 1
    assert collisions[0]["key"] == "llm_response"
    assert collisions[0]["old_step_id"] == "1"
    assert collisions[0]["new_step_id"] == "2"


def test_apply_step_result_outputs_deep_copied():
    data = _empty_data()
    result_data = {"nested": {"value": 1}}
    apply_step_result(data, step_id=1, step_type="llm_call", label=None, result_data=result_data)

    # Mutating the original should not affect the canonical record
    result_data["nested"]["value"] = 999
    assert data["steps"]["by_id"]["1"]["outputs"]["nested"]["value"] == 1


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
        label="Ask User",
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=False,
        channel="pwa_popup_text",
        action="escalate",
    )

    assert data["interactive_response"] == payload
    assert "5" in data["steps"]["by_id"]


def test_apply_interactive_response_auto_escalate_on_escalate():
    data = _empty_data()
    payload = {"channel": "pwa_popup_text", "action": "escalate", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label=None,
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=True,
        channel="pwa_popup_text",
        action="escalate",
    )

    assert data.get("auto_escalate_triggered") is True


def test_apply_interactive_response_auto_escalate_on_timeout():
    data = _empty_data()
    payload = {"channel": "timeout", "action": "escalate", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label=None,
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=True,
        channel="timeout",
        action="escalate",
    )

    assert data.get("auto_escalate_triggered") is True


def test_apply_interactive_response_no_auto_escalate_on_dismiss():
    data = _empty_data()
    payload = {"channel": "pwa_popup_text", "action": "dismiss", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label=None,
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=True,
        channel="pwa_popup_text",
        action="dismiss",
    )

    assert "auto_escalate_triggered" not in data


def test_apply_interactive_response_auto_escalate_disabled():
    data = _empty_data()
    payload = {"channel": "pwa_popup_text", "action": "escalate", "timestamp": "x", "raw_response": {}}
    apply_interactive_response(
        data,
        step_id=5,
        step_type="interactive_prompt",
        label=None,
        output_key="interactive_response",
        response_payload=payload,
        auto_escalate=False,
        channel="pwa_popup_text",
        action="escalate",
    )

    assert "auto_escalate_triggered" not in data


# ---------------------------------------------------------------------------
# copy_pipeline_snapshot
# ---------------------------------------------------------------------------


def test_copy_pipeline_snapshot_deep_copies():
    data = {"nested": {"value": 1}, "steps": {"by_id": {"1": {"outputs": {"x": 2}}}}}
    snapshot = copy_pipeline_snapshot(data)

    # Mutate original
    data["nested"]["value"] = 999
    data["steps"]["by_id"]["1"]["outputs"]["x"] = 999

    assert snapshot["nested"]["value"] == 1
    assert snapshot["steps"]["by_id"]["1"]["outputs"]["x"] == 2


def test_copy_pipeline_snapshot_is_independent():
    data = {"a": [1, 2, 3]}
    snapshot = copy_pipeline_snapshot(data)
    data["a"].append(4)

    assert snapshot["a"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# resolve_pipeline_value
# ---------------------------------------------------------------------------


def test_resolve_pipeline_value_top_level():
    data = {"vision_response": "hello"}
    assert resolve_pipeline_value(data, "vision_response") == "hello"


def test_resolve_pipeline_value_dotted_path():
    data = {"steps": {"by_id": {"12": {"outputs": {"vision_response": {"summary": "ok"}}}}}}
    result = resolve_pipeline_value(data, "steps.by_id.12.outputs.vision_response.summary")
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
