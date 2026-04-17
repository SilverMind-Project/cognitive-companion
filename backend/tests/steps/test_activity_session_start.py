"""Unit tests for :class:`~backend.steps.builtin.activity_session_start.ActivitySessionStartHandler`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import MagicMock

from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.activity_session_start import ActivitySessionStartHandler

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


def _make_mock_service() -> MagicMock:
    svc = MagicMock()
    svc.open_session = MagicMock(
        return_value=MagicMock(
            session_id="grandma_sleep_2026-04-15T01:00:00",
            person_id="grandma",
            activity_type="sleep",
            room_name="Bedroom",
            opened_at=datetime.now(UTC),
            timeout_minutes=720,
            was_existing=False,
        )
    )
    return svc


def _make_services(activity_session_service=None) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        activity_session_service=activity_session_service,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


handler = ActivitySessionStartHandler()


class TestMetadata:
    def test_returns_metadata(self):
        meta = handler.metadata()
        assert meta.type_name == "activity_session_start"
        assert meta.category == "action"
        assert meta.display_name == "Start Activity Session"
        assert "activity_type" in meta.config_schema["properties"]
        assert "output_key" in meta.config_schema["properties"]

    def test_default_config(self):
        assert handler.metadata().default_config["activity_type"] == ""
        assert handler.metadata().default_config["output_key"] == "session"


class TestExecute:
    async def test_opens_new_session(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep", "person_id": "grandma", "room_name": "Bedroom"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert "session" in result.data
        assert result.data["session"]["person_id"] == "grandma"
        assert result.data["session"]["activity_type"] == "sleep"
        assert result.data["session"]["was_existing"] is False
        svc.open_session.assert_called_once()

    async def test_idempotent_reuses_existing(self):
        svc = _make_mock_service()
        svc.open_session.return_value.was_existing = True
        step = _make_step({"activity_type": "sleep", "person_id": "grandma"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert result.data["session"]["was_existing"] is True

    async def test_custom_output_key(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "bathroom",
            "person_id": "grandma",
            "output_key": "bathroom_session",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert "bathroom_session" in result.data
        assert "session" not in result.data

    async def test_template_person_id(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "person_id": "{{person_detections.0.person_id}}",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"person_detections": [{"person_id": "grandma"}]},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        svc.open_session.assert_called_once()
        assert svc.open_session.call_args.kwargs["person_id"] == "grandma"

    async def test_template_room_name(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "room_name": "{{room_transitions.0.to_room}}",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"room_transitions": [{"to_room": "Bedroom"}]},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        svc.open_session.assert_called_once()
        assert svc.open_session.call_args.kwargs["room_name"] == "Bedroom"

    async def test_template_timeout(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "timeout_minutes": "{{config.sleep_timeout}}",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"config": {"sleep_timeout": 600}},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert svc.open_session.call_args.kwargs["timeout_minutes"] == 600

    async def test_no_service_returns_error(self):
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(None),
        )
        assert result.success
        assert "error" in result.data["session"]

    async def test_default_person_id_unknown(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert svc.open_session.call_args.kwargs["person_id"] == "unknown"

    async def test_default_room_from_trigger(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(room_name="Living Room"),
            services=_make_services(svc),
        )
        assert result.success
        assert svc.open_session.call_args.kwargs["room_name"] == "Living Room"

    async def test_confidence_from_template(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "confidence": "{{detection.confidence}}",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"detection": {"confidence": "0.95"}},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert svc.open_session.call_args.kwargs["confidence"] == 0.95

    async def test_confidence_invalid_defaults(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "confidence": "not_a_number",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        # Should default to 0.85
        assert svc.open_session.call_args.kwargs["confidence"] == 0.85

    async def test_metadata_extra_json(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "metadata_extra": '{"source": "camera", "door": "front"}',
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        call_kwargs = svc.open_session.call_args.kwargs
        assert call_kwargs["metadata"] == {"source": "camera", "door": "front"}

    async def test_metadata_extra_template(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "metadata_extra": '{"reason": "{{logic_response.reason}}"}',
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"logic_response": {"reason": "mmWave sensor"}},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        call_kwargs = svc.open_session.call_args.kwargs
        assert call_kwargs["metadata"] == {"reason": "mmWave sensor"}

    async def test_activity_type_defaults_to_other(self):
        svc = _make_mock_service()
        step = _make_step({})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert svc.open_session.call_args.kwargs["activity_type"] == "other"

    async def test_session_id_in_result(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep", "person_id": "grandma"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(svc),
        )
        assert result.success
        assert result.data["session"]["session_id"] == "grandma_sleep_2026-04-15T01:00:00"
        assert result.data["session"]["timeout_minutes"] == 720
