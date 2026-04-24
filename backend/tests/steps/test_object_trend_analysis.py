"""Unit tests for :class:`~backend.steps.builtin.object_trend_analysis.ObjectTrendAnalysisHandler`.

Tests the step's graceful degradation when the client is missing, severity
threshold filtering, room ID resolution from trigger context, and summary
generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from backend.integrations.semantic_memory_client import (
    RoomTrendResult,
    SemanticMemoryClient,
    TrendSnapshot,
)
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


def _make_services(semantic_memory_client=None) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        semantic_memory_client=semantic_memory_client,
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
    client = AsyncMock(spec=SemanticMemoryClient)
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
    def test_metadata(self):
        meta = _HANDLER.metadata()
        assert meta.type_name == "object_trend_analysis"
        assert meta.display_name == "Object Trend Analysis"
        assert meta.category == "perception"
        assert meta.icon == "mdi-chart-line"


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestExecute:
    async def test_no_client_returns_empty(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        services = _make_services(semantic_memory_client=None)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.success is True
        assert result.data["room_trends"] == {}
        assert result.data["room_trends_any_warning"] is False
        assert result.data["room_trends_max_severity"] == "ok"
        assert result.data["room_trends_summary"] == "No trend data available."

    async def test_empty_room_ids_returns_empty(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger(room_name=None)
        client = _mock_client()
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.success is True
        assert result.data["room_trends"] == {}

    async def test_triggers_room_name_as_room_id(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger(room_name="Kitchen")
        client = _mock_client()
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert len(result.data["room_trends"]) == 1
        assert "Kitchen" in result.data["room_trends"]

    async def test_config_room_ids_override_trigger(self):
        step = _make_step(config={"room_ids": ["Bedroom"]})
        execution = _FakeExecution()
        trigger = _make_trigger(room_name="Kitchen")
        client = _mock_client(results={"Bedroom": _mock_trend_result(room_id="Bedroom")})
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert "Bedroom" in result.data["room_trends"]
        assert "Kitchen" not in result.data["room_trends"]

    async def test_severity_threshold_filters_anomalies(self):
        step = _make_step(config={"severity_threshold": "warning"})
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    anomalies=[
                        {"severity": "ok", "message": "low"},
                        {"severity": "warning", "message": "mid"},
                        {"severity": "critical", "message": "high"},
                    ],
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        kitchen = result.data["room_trends"]["Kitchen"]
        anomaly_severities = [a["severity"] for a in kitchen["anomalies"]]
        assert "ok" not in anomaly_severities
        assert "warning" in anomaly_severities
        assert "critical" in anomaly_severities

    async def test_max_severity_is_critical(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    overall_severity="critical",
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.data["room_trends_max_severity"] == "critical"

    async def test_max_severity_is_warning(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    overall_severity="warning",
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.data["room_trends_max_severity"] == "warning"

    async def test_any_warning_is_true(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    overall_severity="warning",
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.data["room_trends_any_warning"] is True

    async def test_any_warning_is_false(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    overall_severity="ok",
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.data["room_trends_any_warning"] is False

    async def test_output_key_config(self):
        step = _make_step(config={"output_key": "custom_key"})
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client()
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert "custom_key" in result.data
        assert "room_trends" not in result.data

    async def test_multiple_rooms(self):
        step = _make_step(config={"room_ids": ["Kitchen", "Bedroom"]})
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(room_id="Kitchen"),
                "Bedroom": _mock_trend_result(room_id="Bedroom"),
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert "Kitchen" in result.data["room_trends"]
        assert "Bedroom" in result.data["room_trends"]

    async def test_room_with_no_result_skipped(self):
        step = _make_step(config={"room_ids": ["Kitchen", "Missing"]})
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(results={"Kitchen": _mock_trend_result(room_id="Kitchen")})
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert "Kitchen" in result.data["room_trends"]
        assert "Missing" not in result.data["room_trends"]

    async def test_client_error_returns_empty(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client()
        client.get_room_trends = AsyncMock(side_effect=Exception("service unavailable"))
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.data["room_trends"] == {}

    async def test_summary_text_generated(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    clutter_score=1.5,
                    trend_direction="increasing",
                    overall_severity="warning",
                    persistent_objects=["stove", "fridge"],
                    novel_objects=["cardboard box"],
                    anomalies=[{"severity": "warning", "message": "clutter"}],
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        summary = result.data["room_trends_summary"]
        assert "Kitchen" in summary
        assert "increasing" in summary.lower()
        assert "warning" in summary.lower()

    async def test_include_snapshots(self):
        step = _make_step(config={"include_snapshots_hours": 12})
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client()
        snapshots = [
            TrendSnapshot(
                room_id="Kitchen",
                period_start=datetime(2026, 4, 17, 2, tzinfo=UTC),
                unique_object_count=5,
                object_counts={"stove": 3},
            )
        ]
        client.get_snapshots = AsyncMock(return_value=snapshots)
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        kitchen = result.data["room_trends"]["Kitchen"]
        assert "snapshots" in kitchen
        assert len(kitchen["snapshots"]) == 1

    async def test_snapshots_empty_when_not_configured(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client()
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        kitchen = result.data["room_trends"]["Kitchen"]
        assert "snapshots" not in kitchen

    async def test_persistent_and_novel_objects(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    persistent_objects=["stove", "fridge"],
                    novel_objects=["cardboard box"],
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        kitchen = result.data["room_trends"]["Kitchen"]
        assert kitchen["persistent_objects"] == ["stove", "fridge"]
        assert kitchen["novel_objects"] == ["cardboard box"]

    async def test_baseline_available_false(self):
        """Handler ignores baseline_available; verifies room still returned."""
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    baseline_available=False,
                    clutter_score=0.5,
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        kitchen = result.data["room_trends"]["Kitchen"]
        assert kitchen["clutter_score"] == 0.5
        assert "baseline_available" not in kitchen

    async def test_clutter_score_and_direction(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    clutter_score=2.3,
                    trend_direction="decreasing",
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        kitchen = result.data["room_trends"]["Kitchen"]
        assert kitchen["clutter_score"] == 2.3
        assert kitchen["trend_direction"] == "decreasing"

    async def test_stable_severity_ok_no_warning(self):
        step = _make_step()
        execution = _FakeExecution()
        trigger = _make_trigger()
        client = _mock_client(
            results={
                "Kitchen": _mock_trend_result(
                    room_id="Kitchen",
                    overall_severity="ok",
                    trend_direction="stable",
                )
            }
        )
        services = _make_services(semantic_memory_client=client)
        result = await _HANDLER.execute(step, execution, {}, trigger, services)
        assert result.data["room_trends_any_warning"] is False
        assert result.data["room_trends_max_severity"] == "ok"
