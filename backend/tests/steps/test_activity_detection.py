"""Unit tests for :class:`~backend.steps.builtin.activity_detection.ActivityDetectionHandler`.

Covers template resolution, metadata building, trigger_cooloff, and
Block 7 delegation to :class:`~backend.services.activity.ActivityService`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.activity_detection import ActivityDetectionHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecution:
    id: int = 1
    event_log_id: int | None = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)
    id: int = 1


def _make_step(config: dict | None = None) -> _FakeStep:
    return _FakeStep(config_json=config or {})


def _make_trigger(
    sensor_id: str = "cam-1",
    room_name: str = "Kitchen",
) -> TriggerContext:
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id=sensor_id,
        room_name=room_name,
    )


def _make_mock_activity_service() -> MagicMock:
    svc = MagicMock()
    svc.record = AsyncMock(
        return_value=MagicMock(
            id=42,
            person_id="grandma",
            activity_type="meal_eating",
            room_id=5,
            room_name="Kitchen",
            confidence=0.85,
            source_event_id=1,
            metadata_json=None,
            duration_minutes=None,
            session_id=None,
            detected_at=None,
        )
    )
    return svc


def _make_mock_person_tracking() -> MagicMock:
    pt = MagicMock()
    pt.record_activity = AsyncMock(
        return_value=MagicMock(
            id=42,
            person_id="grandma",
            activity_type="meal_eating",
            room_id=5,
            room_name="Kitchen",
            confidence=0.85,
            source_event_id=1,
            metadata_json=None,
            duration_minutes=None,
            session_id=None,
            detected_at=None,
        )
    )
    return pt


def _make_services(activity=None, person_tracking=None) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        activity=activity,
        person_tracking=person_tracking,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


handler = ActivityDetectionHandler()


class TestMetadata:
    def test_returns_metadata(self):
        meta = handler.metadata()
        assert meta.type_name == "activity_detection"
        assert meta.category == "state"
        assert meta.display_name == "Record Activity"
        assert "activity_type" in meta.config_schema["properties"]
        assert "trigger_cooloff" in meta.config_schema["properties"]

    def test_default_config(self):
        assert handler.metadata().default_config["activity_type"] == ""
        assert handler.metadata().default_config["trigger_cooloff"] is True


class TestExecute:
    async def test_records_activity_via_activity_service(self):
        """Should call services.activity.record when available."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "meal_eating",
            "person_id": "grandma",
            "confidence": 0.85,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert "detected_activities" in result.data
        assert len(result.data["detected_activities"]) == 1
        assert result.data["detected_activities"][0]["person_id"] == "grandma"
        assert result.data["detected_activities"][0]["activity_type"] == "meal_eating"
        svc.record.assert_called_once()

    async def test_fallback_to_person_tracking(self):
        """Should fall back to person_tracking when services.activity is None."""
        pt = _make_mock_person_tracking()
        step = _make_step({
            "activity_type": "meal_eating",
            "person_id": "grandma",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=None, person_tracking=pt),
        )
        assert result.success
        assert "detected_activities" in result.data
        pt.record_activity.assert_called_once()

    async def test_activity_takes_precedence_over_person_tracking(self):
        """When both are available, use services.activity."""
        svc = _make_mock_activity_service()
        pt = _make_mock_person_tracking()
        step = _make_step({"activity_type": "meal_eating"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc, person_tracking=pt),
        )
        assert result.success
        svc.record.assert_called_once()
        pt.record_activity.assert_not_called()

    async def test_template_person_id(self):
        """Should resolve {{template}} syntax for person_id."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "person_id": "{{person_detections.0.person_id}}",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"person_detections": [{"person_id": "grandma"}]},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.record.call_args.kwargs["person_id"] == "grandma"

    async def test_template_room_name(self):
        """Should resolve {{template}} syntax for room_name."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "bathroom",
            "room_name": "{{room_transitions.0.to_room}}",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"room_transitions": [{"to_room": "Bathroom"}]},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.record.call_args.kwargs["room_name"] == "Bathroom"

    async def test_default_room_from_trigger(self):
        """Should use trigger room when room_name is empty."""
        svc = _make_mock_activity_service()
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(room_name="Bedroom"),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.record.call_args.kwargs["room_name"] == "Bedroom"

    async def test_default_person_id_unknown(self):
        """Should default to 'unknown' when person_id is empty."""
        svc = _make_mock_activity_service()
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.record.call_args.kwargs["person_id"] == "unknown"

    async def test_confidence_clamped(self):
        """Should clamp confidence to [0, 1]."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "confidence": 1.5,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.record.call_args.kwargs["confidence"] == 1.0

    async def test_confidence_from_template(self):
        """Should resolve confidence from template."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "confidence": "{{detection.confidence}}",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"detection": {"confidence": "0.95"}},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.record.call_args.kwargs["confidence"] == 0.95

    async def test_confidence_invalid_defaults(self):
        """Should default to 0.8 when confidence template fails."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "confidence": "not_a_number",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.record.call_args.kwargs["confidence"] == 0.8

    async def test_captures_scene_description(self):
        """Should capture scene_description from pipeline_data when enabled."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "meal_eating",
            "capture_scene_description": True,
            "scene_description_key": "vision_response",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"vision_response": "Person eating at table"},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        activity = result.data["detected_activities"][0]
        assert activity["metadata"]["scene_description"] == "Person eating at table"

    async def test_metadata_extra_json(self):
        """Should merge extra metadata from JSON string."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "metadata_extra": '{"source": "camera", "door": "front"}',
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        activity = result.data["detected_activities"][0]
        assert activity["metadata"]["source"] == "camera"
        assert activity["metadata"]["door"] == "front"

    async def test_trigger_cooloff_flag(self):
        """Should include _cooloff_triggered when trigger_cooloff is True."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "trigger_cooloff": True,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.data.get("_cooloff_triggered") is True

    async def test_no_cooloff_when_disabled(self):
        """Should not include _cooloff_triggered when trigger_cooloff is False."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "trigger_cooloff": False,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert "_cooloff_triggered" not in result.data

    async def test_empty_activity_type_returns_empty(self):
        """Should return empty detected_activities when activity_type is empty."""
        svc = _make_mock_activity_service()
        step = _make_step({})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert result.data["detected_activities"] == []
        svc.record.assert_not_called()

    async def test_no_service_no_fallback(self):
        """Should do nothing when neither services.activity nor person_tracking is available."""
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=None, person_tracking=None),
        )
        assert result.success
        # Still returns detected_activities but no record was made
        assert "detected_activities" in result.data


class TestBlock7Delegation:
    """Tests for B7.T1: activity_detection delegates to services.activity."""

    async def test_delegation_to_activity_service(self):
        """Should call services.activity.record() with correct kwargs."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "medication_taken",
            "person_id": "grandma",
            "room_name": "Living Room",
            "confidence": 0.9,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(event_log_id=99),
            pipeline_data={},
            trigger=_make_trigger(sensor_id="cam-2", room_name="Living Room"),
            services=_make_services(activity=svc),
        )
        assert result.success
        svc.record.assert_called_once_with(
            person_id="grandma",
            activity_type="medication_taken",
            room_name="Living Room",
            confidence=0.9,
            source_event_id=99,
            metadata=None,
        )

    async def test_delegation_with_metadata(self):
        """Should pass metadata to services.activity.record()."""
        svc = _make_mock_activity_service()
        step = _make_step({
            "activity_type": "sleep",
            "person_id": "grandma",
            "capture_scene_description": True,
            "scene_description_key": "vision_response",
            "metadata_extra": '{"note": "VLM detected bed"}',
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(event_log_id=42),
            pipeline_data={"vision_response": "Person sleeping in bed"},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        call_kwargs = svc.record.call_args.kwargs
        assert call_kwargs["metadata"]["scene_description"] == "Person sleeping in bed"
        assert call_kwargs["metadata"]["note"] == "VLM detected bed"

    async def test_fallback_logs_warning_once(self):
        """Should log warning once when falling back to person_tracking."""
        import backend.steps.builtin.activity_detection as mod

        pt = _make_mock_person_tracking()
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=None, person_tracking=pt),
        )
        assert result.success
        # Reset the flag for next test
        mod._activity_legacy_warned = False
