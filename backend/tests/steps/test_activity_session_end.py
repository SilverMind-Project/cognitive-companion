"""Unit tests for :class:`~backend.steps.builtin.activity_session_end.ActivitySessionEndHandler`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.activity_session_end import ActivitySessionEndHandler

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


def _make_trigger(sensor_id: str = "cam-1", room_name: str = "Bedroom") -> TriggerContext:
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id=sensor_id,
        room_name=room_name,
    )


def _make_mock_close_result() -> MagicMock:
    return MagicMock(
        session_id="grandma_sleep_2026-04-15T01:00:00",
        person_id="grandma",
        activity_type="sleep",
        room_name="Bedroom",
        opened_at=datetime.now(UTC),
        closed_at=datetime.now(UTC),
        duration_minutes=480,
        status="closed",
        closed_via="explicit",
    )


def _make_mock_service(closed_result=None, raise_on_close=False) -> MagicMock:
    svc = MagicMock()
    if raise_on_close:
        svc.close_session = MagicMock(side_effect=ValueError("No open session found"))
    else:
        svc.close_session = MagicMock(return_value=closed_result or _make_mock_close_result())
    svc.record = AsyncMock()
    return svc


def _make_services(
    person_tracking=None,
    activity=None,
) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        person_tracking=person_tracking,
        activity=activity,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


handler = ActivitySessionEndHandler()


class TestMetadata:
    def test_returns_metadata(self):
        meta = handler.metadata()
        assert meta.type_name == "activity_session_end"
        assert meta.category == "action"
        assert meta.display_name == "End Activity Session"

    def test_default_config(self):
        assert handler.metadata().default_config["activity_type"] == ""
        assert handler.metadata().default_config["write_activity_record"] is True
        assert handler.metadata().default_config["output_key"] == "closed_session"


class TestExecute:
    async def test_closes_session(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep", "person_id": "grandma"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert "closed_session" in result.data
        assert result.data["closed_session"]["duration_minutes"] == 480
        assert result.data["closed_session"]["closed_via"] == "explicit"
        svc.close_session.assert_called_once()

    async def test_no_open_session_returns_error(self):
        svc = _make_mock_service(raise_on_close=True)
        step = _make_step({"activity_type": "sleep", "person_id": "grandma"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert not result.success
        assert "error" in result.data["closed_session"]
        assert result.data["closed_session"]["no_open_session"] is True

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
        assert "error" in result.data["closed_session"]

    async def test_template_activity_type(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "{{logic_response.activity}}"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"logic_response": {"activity": "bathroom"}},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.close_session.call_args.kwargs["activity_type"] == "bathroom"

    async def test_custom_output_key(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "output_key": "sleep_result",
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert "sleep_result" in result.data
        assert "closed_session" not in result.data

    async def test_writes_person_activity(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "person_id": "grandma",
            "write_activity_record": True,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        svc.record.assert_called_once()
        call_kwargs = svc.record.call_args.kwargs
        assert call_kwargs["metadata"]["duration_minutes"] == 480

    async def test_skips_person_activity_when_disabled(self):
        svc = _make_mock_service()
        step = _make_step({
            "activity_type": "sleep",
            "write_activity_record": False,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        svc.record.assert_not_called()

    async def test_result_contains_duration(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep", "person_id": "grandma"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert result.data["closed_session"]["duration_minutes"] == 480
        assert result.data["closed_session"]["status"] == "closed"

    async def test_person_id_from_template(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep", "person_id": "{{person_detections.0.person_id}}"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={"person_detections": [{"person_id": "grandma"}]},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.close_session.call_args.kwargs["person_id"] == "grandma"

    async def test_default_person_id_unknown(self):
        svc = _make_mock_service()
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=svc),
        )
        assert result.success
        assert svc.close_session.call_args.kwargs["person_id"] == "unknown"


# ---------------------------------------------------------------------------
# Block 7: delegation to services.activity
# ---------------------------------------------------------------------------


class TestBlock7Delegation:
    """Tests for B7.T3: activity_session_end delegates to services.activity."""

    async def test_delegates_close_to_activity_service(self):
        """Should call services.activity.close_session when available."""
        mock_svc = MagicMock()
        mock_svc.close_session = MagicMock(return_value=_make_mock_close_result())
        mock_svc.record = AsyncMock()
        step = _make_step({"activity_type": "sleep", "person_id": "grandma"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=mock_svc),
        )
        assert result.success
        assert "closed_session" in result.data
        mock_svc.close_session.assert_called_once()

    async def test_delegates_record_to_activity_service(self):
        """Should call services.activity.record for write_activity_record when using activity service."""
        mock_svc = MagicMock()
        mock_svc.close_session = MagicMock(return_value=_make_mock_close_result())
        mock_svc.record = AsyncMock()
        step = _make_step({
            "activity_type": "sleep",
            "person_id": "grandma",
            "write_activity_record": True,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=mock_svc),
        )
        assert result.success
        mock_svc.record.assert_called_once()
        call_kwargs = mock_svc.record.call_args.kwargs
        assert call_kwargs["metadata"]["duration_minutes"] == 480

    async def test_activity_takes_precedence_over_legacy(self):
        """When both services.activity and legacy services are set, use activity."""
        mock_svc = MagicMock()
        mock_svc.close_session = MagicMock(return_value=_make_mock_close_result())
        mock_svc.record = AsyncMock()
        legacy_svc = MagicMock()
        legacy_svc.close_session = MagicMock(return_value=_make_mock_close_result())
        legacy_svc.person_tracking = MagicMock()
        legacy_svc.person_tracking.record_activity = AsyncMock()
        step = _make_step({
            "activity_type": "sleep",
            "person_id": "grandma",
            "write_activity_record": True,
        })
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(
                activity=mock_svc,
            ),
        )
        assert result.success
        mock_svc.close_session.assert_called_once()
        mock_svc.record.assert_called_once()

    async def test_no_service_returns_error(self):
        """Should return error when services.activity is None."""
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=None),
        )
        assert result.success
        assert "error" in result.data["closed_session"]

    async def test_no_open_session_error(self):
        """Should return no_open_session error when close_session raises ValueError."""
        mock_svc = MagicMock()
        mock_svc.close_session = MagicMock(side_effect=ValueError("No open session found"))
        step = _make_step({"activity_type": "sleep"})
        result = await handler.execute(
            step=step,
            execution=_FakeExecution(),
            pipeline_data={},
            trigger=_make_trigger(),
            services=_make_services(activity=mock_svc),
        )
        assert not result.success
        assert result.data["closed_session"]["no_open_session"] is True
