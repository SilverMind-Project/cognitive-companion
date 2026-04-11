"""Tests for ``WorkflowPipeline`` — sensor event to pipeline execution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.pipeline import WorkflowExecution
from backend.models.room import Room
from backend.models.sensor import Sensor
from backend.services.workflow import WorkflowPipeline


def _make_sensor(db, sensor_id="cam1", room_name="Kitchen", enabled=True) -> Sensor:
    room = Room(name=room_name)
    db.add(room)
    db.flush()
    sensor = Sensor(
        id=sensor_id,
        name=sensor_id,
        sensor_type="camera",
        enabled=enabled,
        room_id=room.id,
    )
    db.add(sensor)
    db.flush()
    return sensor


def _execution(rule_id: int = 1) -> WorkflowExecution:
    return WorkflowExecution(rule_id=rule_id, status="completed")


# ---------------------------------------------------------------------------
# process_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_unknown_sensor(db_session) -> None:
    rules_engine = MagicMock()
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock()

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_event(
        sensor_id="missing",
        media_paths=[],
        media_type="image",
        db=db_session,
    )
    assert result == []
    rules_engine.get_matching_rules.assert_not_called()


@pytest.mark.asyncio
async def test_process_event_disabled_sensor(db_session) -> None:
    _make_sensor(db_session, enabled=False)
    rules_engine = MagicMock()
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock()

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_event(
        sensor_id="cam1", media_paths=[], media_type="image", db=db_session
    )
    assert result == []


@pytest.mark.asyncio
async def test_process_event_no_matching_rules(db_session) -> None:
    _make_sensor(db_session)
    rules_engine = MagicMock()
    rules_engine.get_matching_rules.return_value = []
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock()

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_event(
        sensor_id="cam1", media_paths=[], media_type="image", db=db_session
    )
    assert result == []
    pipeline_executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_event_executes_matched_rules(db_session) -> None:
    _make_sensor(db_session)
    rule1 = MagicMock(id=1, name="rule1", max_concurrent_executions=0)
    rule2 = MagicMock(id=2, name="rule2", max_concurrent_executions=0)
    rules_engine = MagicMock()
    rules_engine.get_matching_rules.return_value = [rule1, rule2]
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock(side_effect=[_execution(1), _execution(2)])

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_event(
        sensor_id="cam1",
        media_paths=["/tmp/a.jpg"],
        media_type="image",
        db=db_session,
    )
    assert len(result) == 2
    assert pipeline_executor.execute.await_count == 2
    trigger = pipeline_executor.execute.await_args_list[0].args[1]
    assert trigger.trigger_type == "sensor_event"
    assert trigger.sensor_id == "cam1"
    assert trigger.room_name == "Kitchen"
    assert trigger.media_paths == ["/tmp/a.jpg"]


@pytest.mark.asyncio
async def test_process_event_sensor_without_room(db_session) -> None:
    sensor = Sensor(id="orphan", name="orphan", sensor_type="camera", enabled=True)
    db_session.add(sensor)
    db_session.flush()

    rules_engine = MagicMock()
    rules_engine.get_matching_rules.return_value = [
        MagicMock(id=1, name="rule", max_concurrent_executions=0)
    ]
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock(return_value=_execution(1))

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    await pipeline.process_event(
        sensor_id="orphan", media_paths=[], media_type="image", db=db_session
    )
    trigger = pipeline_executor.execute.await_args.args[1]
    assert trigger.room_name == "Unknown"


@pytest.mark.asyncio
async def test_process_event_exception_is_logged_not_raised(db_session) -> None:
    _make_sensor(db_session)
    rule_ok = MagicMock(id=1, name="ok", max_concurrent_executions=0)
    rule_bad = MagicMock(id=2, name="bad", max_concurrent_executions=0)
    rules_engine = MagicMock()
    rules_engine.get_matching_rules.return_value = [rule_ok, rule_bad]
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock(side_effect=[_execution(1), RuntimeError("boom")])

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_event(
        sensor_id="cam1", media_paths=[], media_type="image", db=db_session
    )
    # Only the successful execution is returned.
    assert len(result) == 1
    assert result[0].rule_id == 1


# ---------------------------------------------------------------------------
# process_occupancy_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_occupancy_no_matches(db_session) -> None:
    sensor = _make_sensor(db_session)
    rules_engine = MagicMock()
    rules_engine.get_matching_rules.return_value = []
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock()

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_occupancy_event(
        sensor=sensor, room_name="Kitchen", duration_minutes=15, db=db_session
    )
    assert result == []


@pytest.mark.asyncio
async def test_process_occupancy_executes_rules(db_session) -> None:
    sensor = _make_sensor(db_session)
    rule = MagicMock(id=1, name="occupancy", max_concurrent_executions=0)
    rules_engine = MagicMock()
    rules_engine.get_matching_rules.return_value = [rule]
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock(return_value=_execution(1))

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_occupancy_event(
        sensor=sensor, room_name="Kitchen", duration_minutes=20, db=db_session
    )
    assert len(result) == 1
    rules_engine.get_matching_rules.assert_called_once()
    kwargs = rules_engine.get_matching_rules.call_args.kwargs
    assert kwargs["trigger_type"] == "occupancy_duration"
    assert kwargs["occupancy_minutes"] == 20
    trigger = pipeline_executor.execute.await_args.args[1]
    assert trigger.trigger_type == "occupancy_duration"
    assert trigger.occupancy_duration_minutes == 20


@pytest.mark.asyncio
async def test_process_occupancy_logs_exception(db_session) -> None:
    sensor = _make_sensor(db_session)
    rule = MagicMock(id=1, name="occupancy", max_concurrent_executions=0)
    rules_engine = MagicMock()
    rules_engine.get_matching_rules.return_value = [rule]
    pipeline_executor = MagicMock()
    pipeline_executor.execute = AsyncMock(side_effect=RuntimeError("boom"))

    pipeline = WorkflowPipeline(rules_engine, pipeline_executor)
    result = await pipeline.process_occupancy_event(
        sensor=sensor, room_name="Kitchen", duration_minutes=15, db=db_session
    )
    assert result == []
