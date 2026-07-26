"""Unit tests for :class:`~backend.steps.builtin.novelty_gate.NoveltyGateHandler`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import ServiceContainer, StepResult, TriggerContext
from backend.steps.builtin.novelty_gate import NoveltyGateHandler


@dataclass
class _FakeRule:
    name: str = "test_rule"


@dataclass
class _FakeExecution:
    id: int = 1
    rule: object = field(default_factory=_FakeRule)


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


class _FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def _make_trigger(sensor_id: str = "cam-1") -> TriggerContext:
    return TriggerContext(trigger_type="sensor_event", sensor_id=sensor_id, room_name="Kitchen")


def _make_services() -> ServiceContainer:
    return ServiceContainer(db_factory=MagicMock())


async def _run(
    handler: NoveltyGateHandler,
    embedding: list | None,
    config: dict | None = None,
    trigger: TriggerContext | None = None,
) -> StepResult:
    pipeline_data: dict = {"scene_embedding": embedding} if embedding is not None else {}
    return await handler.execute(
        _FakeStep(config_json=config or {}),
        _FakeExecution(),
        pipeline_data,
        trigger or _make_trigger(),
        _make_services(),
    )


class TestMetadata:
    def test_type_name(self) -> None:
        assert NoveltyGateHandler().metadata().type_name == "novelty_gate"

    def test_gate_safe(self) -> None:
        assert NoveltyGateHandler().metadata().gate_safe is True


class TestNoveltyGate:
    @pytest.mark.asyncio
    async def test_first_call_is_novel(self) -> None:
        handler = NoveltyGateHandler()
        result = await _run(handler, [1.0, 0.0], {"min_distance": 0.06})
        assert result.data["novel"] is True
        assert result.data["reason"] == "no_previous"
        assert result.data["distance"] is None

    @pytest.mark.asyncio
    async def test_unchanged_embedding_suppressed(self) -> None:
        handler = NoveltyGateHandler()
        config = {"min_distance": 0.06}
        await _run(handler, [1.0, 0.0], config)
        result = await _run(handler, [1.0, 0.0], config)
        assert result.data["novel"] is False
        assert result.data["reason"] == "compared"
        assert result.data["distance"] == pytest.approx(0.0, abs=1e-9)

    @pytest.mark.asyncio
    async def test_drifted_past_threshold_is_novel_and_cache_updated_only_then(self) -> None:
        handler = NoveltyGateHandler()
        config = {"min_distance": 0.5}
        await _run(handler, [1.0, 0.0], config)  # seeds cache
        result = await _run(handler, [0.0, 1.0], config)  # orthogonal: distance 1.0
        assert result.data["novel"] is True
        assert result.data["reason"] == "compared"
        assert result.data["distance"] == pytest.approx(1.0)

        # Cache is now the drifted embedding; a repeat is "unchanged".
        result2 = await _run(handler, [0.0, 1.0], config)
        assert result2.data["novel"] is False

    @pytest.mark.asyncio
    async def test_slowly_drifting_scene_under_threshold_stays_suppressed(self) -> None:
        handler = NoveltyGateHandler()
        config = {"min_distance": 0.5}
        await _run(handler, [1.0, 0.0], config)
        # A small drift, still below min_distance: stays suppressed and the
        # cache is NOT updated to the drifted value (update only when novel).
        result = await _run(handler, [0.99, 0.01], config)
        assert result.data["novel"] is False

    @pytest.mark.asyncio
    async def test_ttl_expiry_forces_novel(self) -> None:
        clock = _FakeClock()
        handler = NoveltyGateHandler(time_fn=clock)
        config = {"min_distance": 0.5, "ttl_minutes": 10}
        await _run(handler, [1.0, 0.0], config)
        clock.advance(minutes=11)
        result = await _run(handler, [1.0, 0.0], config)
        assert result.data["novel"] is True
        assert result.data["reason"] == "stale"

    @pytest.mark.asyncio
    async def test_within_ttl_still_compared(self) -> None:
        clock = _FakeClock()
        handler = NoveltyGateHandler(time_fn=clock)
        config = {"min_distance": 0.5, "ttl_minutes": 10}
        await _run(handler, [1.0, 0.0], config)
        clock.advance(minutes=5)
        result = await _run(handler, [1.0, 0.0], config)
        assert result.data["reason"] == "compared"
        assert result.data["novel"] is False

    @pytest.mark.asyncio
    async def test_missing_embedding_fails_open(self) -> None:
        handler = NoveltyGateHandler()
        result = await _run(handler, None)
        assert result.data["novel"] is True
        assert result.data["reason"] == "no_embedding"
        assert result.data["distance"] is None

    @pytest.mark.asyncio
    async def test_empty_embedding_list_fails_open(self) -> None:
        handler = NoveltyGateHandler()
        result = await _run(handler, [])
        assert result.data["novel"] is True
        assert result.data["reason"] == "no_embedding"

    @pytest.mark.asyncio
    async def test_scope_isolation_two_cameras_do_not_share_cache(self) -> None:
        handler = NoveltyGateHandler()
        config = {"min_distance": 0.06}
        await _run(handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-1"))
        # cam-2 has never been seen for this scope: still "no_previous", not "compared".
        result = await _run(handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-2"))
        assert result.data["reason"] == "no_previous"

    @pytest.mark.asyncio
    async def test_custom_embedding_key(self) -> None:
        handler = NoveltyGateHandler()
        pipeline_data = {"steps": {"scene": {"outputs": {"embedding": [1.0, 0.0]}}}}
        result = await handler.execute(
            _FakeStep(
                config_json={
                    "embedding_key": "steps.scene.outputs.embedding",
                    "min_distance": 0.06,
                }
            ),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            _make_services(),
        )
        assert result.data["reason"] == "no_previous"

    @pytest.mark.asyncio
    async def test_settings_default_min_distance_used_when_not_configured(self) -> None:
        handler = NoveltyGateHandler()
        await _run(handler, [1.0, 0.0], {})  # no min_distance override
        # A tiny drift well under the novelty_gate.min_distance setting (0.06).
        result = await _run(handler, [0.999, 0.001], {})
        assert result.data["reason"] == "compared"
        assert result.data["novel"] is False

    @pytest.mark.asyncio
    async def test_output_conforms_to_schema(self) -> None:
        handler = NoveltyGateHandler()
        result = await _run(handler, [1.0, 0.0])
        assert_output_conforms_to_schema(handler, result)


class TestCacheBound:
    @pytest.mark.asyncio
    async def test_cache_size_bounded_evicts_oldest_scope(self) -> None:
        clock = _FakeClock()
        handler = NoveltyGateHandler(time_fn=clock, max_cache_scopes=2)
        config = {"min_distance": 0.06}

        await _run(handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-1"))
        clock.advance(minutes=1)
        await _run(handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-2"))
        assert len(handler._cache) == 2

        # A third distinct scope pushes past the cap: cam-1 (oldest) is evicted.
        clock.advance(minutes=1)
        await _run(handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-3"))
        assert len(handler._cache) == 2

        # cam-1 was evicted, so it's "no_previous" again rather than "compared".
        result = await _run(
            handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-1")
        )
        assert result.data["reason"] == "no_previous"

    @pytest.mark.asyncio
    async def test_repeat_scope_within_cap_does_not_evict(self) -> None:
        handler = NoveltyGateHandler(max_cache_scopes=2)
        config = {"min_distance": 0.06}

        await _run(handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-1"))
        await _run(handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-2"))
        # Re-reading an existing scope must not count as a new key or evict anything.
        result = await _run(
            handler, [1.0, 0.0], config, trigger=_make_trigger(sensor_id="cam-1")
        )
        assert result.data["reason"] == "compared"
        assert len(handler._cache) == 2
