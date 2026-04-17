"""Unit tests for :class:`~backend.steps.builtin.object_trend_analysis.ObjectTrendAnalysisHandler`.

Tests the step's graceful degradation when the client is missing, severity
threshold filtering, room ID resolution from trigger context, and summary
generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from backend.integrations.object_trend_client import ObjectTrendClient, RoomTrendResult
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.object_trend_analysis import ObjectTrendAnalysisHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_step(config: dict | None = None) -> _FakeStep:
    return _FakeStep(config_json=config or {})


def _make_trigger(
    room_name: str | None = "Kitchen",
    sensor_id: str = "cam-1",
) -> TriggerContext:
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id=sensor_id,
        room_name=room_name,
    )


def _make_services(object_trend_client=None) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        object_trend_client=object_trend_client,
    )


def _mock_trend_result(
    room_id: str = "Kitchen",
    clutter_score: float = 0.5,
    trend_direction: str = "stable",
    overall_severity: str = "ok",
    persistent_objects: list[str] | None = None,
    novel_objects: list[str] | None = None,
    anomalies: list[dict] | None = None,
    baseline_available: bool = True,
) -> RoomTrendResult:
    return RoomTrendResult(
        room_id=room_id,
        room_name=room_id.replace("_", " ").title(),
        as_of=datetime(2026, 4, 17, 14, 30, tzinfo=UTC),
        baseline_available=baseline_available,
        clutter_score=clutter_score,
        trend_direction=trend_direction,
        overall_severity=overall_severity,
        persistent_objects=persistent_objects or [],
        novel_objects=novel_objects or [],
        anomalies=anomalies or [],
    )


def _mock_client(
    results: dict[str, RoomTrendResult] | None = None,
) -> AsyncMock:
    client = AsyncMock(spec=ObjectTrendClient)
    if results is None:
        results = {"Kitchen": _mock_trend_result(room_id="Kitchen")}

    async def get_room_trends(room_id: str):
        return results.get(room_id)

    client.get_room_trends = AsyncMock(side_effect=get_room_trends)
    client.get_snapshots = AsyncMock(return_value=[])
    return client


_HANDLER = ObjectTrendAnalysisHandler()

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_type_name(self):
        assert _HANDLER.metadata().type_name == "object_trend_analysis"

    def test_category(self):
        assert _HANDLER.metadata().category == "perception"

    def test_default_config_has_expected_keys(self):
        keys = _HANDLER.metadata().default_config.keys()
        for key in ("room_ids", "include_snapshots_hours", "severity_threshold", "output_key"):
            assert key in keys, f"Missing config key: {key}"

# ---------------------------------------------------------------------------
# Early exits / graceful degradation
# ---------------------------------------------------------------------------


class TestEarlyExits:
    async def test_returns_empty_when_no_client(self):
        services = _make_services(object_trend_client=None)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.success is True
        assert result.data["room_trends"] == {}
        assert result.data["room_trends_any_warning"] is False
        assert result.data["room_trends_max_severity"] == "ok"
        assert "No trend data" in result.data["room_trends_summary"]

    async def test_returns_empty_when_no_room_ids_and_no_trigger_room(self):
        client = _mock_client()
        services = _make_services(object_trend_client=client)
        trigger = _make_trigger(room_name=None)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, trigger, services
        )
        assert result.data["room_trends"] == {}
        client.get_room_trends.assert_not_called()

    async def test_continues_pipeline(self):
        services = _make_services(object_trend_client=None)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.should_continue is True

# ---------------------------------------------------------------------------
# Happy path - single room
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_basic_result_keys(self):
        client = _mock_client({"Kitchen": _mock_trend_result(room_id="Kitchen")})
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        data = result.data
        assert "Kitchen" in data["room_trends"]
        assert "room_trends_any_warning" in data
        assert "room_trends_max_severity" in data
        assert "room_trends_summary" in data

    async def test_clutter_score_passed_through(self):
        client = _mock_client({"Kitchen": _mock_trend_result(room_id="Kitchen", clutter_score=2.5)})
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.data["room_trends"]["Kitchen"]["clutter_score"] == 2.5

    async def test_trend_direction_passed_through(self):
        client = _mock_client({"Kitchen": _mock_trend_result(room_id="Kitchen", trend_direction="increasing")})
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.data["room_trends"]["Kitchen"]["trend_direction"] == "increasing"

    async def test_persistent_objects_passed_through(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(room_id="Kitchen", persistent_objects=["chair", "table"])
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.data["room_trends"]["Kitchen"]["persistent_objects"] == ["chair", "table"]

    async def test_novel_objects_passed_through(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(room_id="Kitchen", novel_objects=["umbrella"])
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.data["room_trends"]["Kitchen"]["novel_objects"] == ["umbrella"]

# ---------------------------------------------------------------------------
# Room ID resolution
# ---------------------------------------------------------------------------


class TestRoomIdResolution:
    async def test_uses_trigger_room_when_room_ids_empty(self):
        client = _mock_client({"Kitchen": _mock_trend_result(room_id="Kitchen")})
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step({"room_ids": []}),
            _FakeExecution(),
            {},
            _make_trigger(room_name="Kitchen"),
            services,
        )
        assert "Kitchen" in result.data["room_trends"]

    async def test_uses_explicit_room_ids_over_trigger(self):
        client = _mock_client({
            "LivingRoom": _mock_trend_result(room_id="LivingRoom"),
            "Kitchen": _mock_trend_result(room_id="Kitchen"),
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step({"room_ids": ["LivingRoom"]}),
            _FakeExecution(),
            {},
            _make_trigger(room_name="Kitchen"),
            services,
        )
        assert "LivingRoom" in result.data["room_trends"]
        assert "Kitchen" not in result.data["room_trends"]

# ---------------------------------------------------------------------------
# Severity threshold filtering
# ---------------------------------------------------------------------------


class TestSeverityThreshold:
    async def test_default_threshold_filters_ok(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(
                overall_severity="ok",
                anomalies=[
                    {"severity": "info", "type": "minor"},
                ],
            )
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step({"severity_threshold": "info"}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        # Info anomalies should be included (>= info threshold)
        assert len(result.data["room_trends"]["Kitchen"]["anomalies"]) == 1

    async def test_warning_threshold_filters_info(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(
                overall_severity="ok",
                anomalies=[
                    {"severity": "info", "type": "minor"},
                    {"severity": "warning", "type": "major"},
                ],
            )
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step({"severity_threshold": "warning"}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        # Only warning+ anomalies should be included
        anomalies = result.data["room_trends"]["Kitchen"]["anomalies"]
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "warning"

    async def test_any_warning_flag(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(overall_severity="warning"),
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert result.data["room_trends_any_warning"] is True

    async def test_max_severity_tracks_highest(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(overall_severity="warning"),
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert result.data["room_trends_max_severity"] == "warning"

    async def test_critical_severity(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(overall_severity="critical"),
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert result.data["room_trends_max_severity"] == "critical"
        assert result.data["room_trends_any_warning"] is True

# ---------------------------------------------------------------------------
# Multiple rooms
# ---------------------------------------------------------------------------


class TestMultipleRooms:
    async def test_queries_all_rooms(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(room_id="Kitchen"),
            "LivingRoom": _mock_trend_result(room_id="LivingRoom", overall_severity="warning"),
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step({"room_ids": ["Kitchen", "LivingRoom"]}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert len(result.data["room_trends"]) == 2
        assert "Kitchen" in result.data["room_trends"]
        assert "LivingRoom" in result.data["room_trends"]

    async def test_max_severity_is_highest_across_rooms(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(room_id="Kitchen", overall_severity="ok"),
            "LivingRoom": _mock_trend_result(room_id="LivingRoom", overall_severity="warning"),
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step({"room_ids": ["Kitchen", "LivingRoom"]}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert result.data["room_trends_max_severity"] == "warning"

# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class TestSnapshots:
    async def test_skips_snapshots_when_include_zero(self):
        client = _mock_client()
        services = _make_services(object_trend_client=client)
        await _HANDLER.execute(
            _make_step({"include_snapshots_hours": 0}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        client.get_snapshots.assert_not_called()

    async def test_fetches_snapshots_when_include_positive(self):
        client = _mock_client()
        services = _make_services(object_trend_client=client)
        await _HANDLER.execute(
            _make_step({"include_snapshots_hours": 12}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        client.get_snapshots.assert_called_once_with("Kitchen", since_hours=12)

# ---------------------------------------------------------------------------
# Custom output_key
# ---------------------------------------------------------------------------


class TestCustomOutputKey:
    async def test_uses_custom_output_key(self):
        client = _mock_client()
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step({"output_key": "trends"}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert "trends" in result.data
        assert "room_trends" not in result.data

# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------


class TestSummary:
    async def test_empty_summary_when_no_trends(self):
        client = _mock_client()
        # Override to return None for all rooms
        async def never_returns(_room_id: str):
            return None
        client.get_room_trends = never_returns
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert "No trend data" in result.data["room_trends_summary"]

    async def test_summary_includes_severity_and_clutter(self):
        client = _mock_client({
            "Kitchen": _mock_trend_result(
                room_id="Kitchen",
                clutter_score=2.3,
                overall_severity="warning",
                trend_direction="increasing",
            )
        })
        services = _make_services(object_trend_client=client)
        result = await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        summary = result.data["room_trends_summary"]
        assert "WARNING" in summary
        assert "Kitchen" in summary
        assert "2.3" in summary
        assert "increasing" in summary
