"""Unit tests for :mod:`backend.steps._helpers`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.steps._helpers import resolve_person_id, resolve_surface_id


class TestResolvePersonId:
    def test_explicit_config_person_id_wins(self):
        assert resolve_person_id({"person_id": "alice"}, {"person_id": "bob"}) == "alice"

    def test_falls_back_to_persons_list(self):
        assert resolve_person_id({}, {"persons": [{"person_id": "alice"}]}) == "alice"

    def test_falls_back_to_persons_list_id_key(self):
        assert resolve_person_id({}, {"persons": [{"id": "alice"}]}) == "alice"

    def test_falls_back_to_scalar_person_id(self):
        assert resolve_person_id({}, {"person_id": "alice"}) == "alice"

    def test_falls_back_to_trigger_event_person_id(self):
        """A dementia_signal-fired pipeline carries person_id only under
        pipeline_data['trigger_event'], not the top-level scalar or persons list."""
        pipeline_data = {"trigger_event": {"person_id": "alice", "signal_kind": "x"}}
        assert resolve_person_id({}, pipeline_data) == "alice"

    def test_config_wins_over_trigger_event(self):
        pipeline_data = {"trigger_event": {"person_id": "alice"}}
        assert resolve_person_id({"person_id": "bob"}, pipeline_data) == "bob"

    def test_nothing_resolvable_returns_none(self):
        assert resolve_person_id({}, {}) is None

    def test_trigger_event_without_person_id_returns_none(self):
        assert resolve_person_id({}, {"trigger_event": {"signal_kind": "x"}}) is None

    def test_templated_config_person_id_is_rendered(self):
        assert (
            resolve_person_id(
                {"person_id": "{{trigger_event.person_id}}"},
                {"trigger_event": {"person_id": "vasanthi-amma"}},
            )
            == "vasanthi-amma"
        )

    def test_templated_person_id_can_use_trigger_vars(self):
        assert (
            resolve_person_id({"person_id": "{{trigger.sensor_id}}"}, {}, {"sensor_id": "cam1"})
            == "cam1"
        )

    def test_unresolved_template_resolves_to_nobody_not_someone_else(self):
        """A named person that does not resolve must not become whoever is first in the
        pipeline (a signal or presence read would then be attributed to the wrong person)."""
        assert (
            resolve_person_id({"person_id": "{{steps.missing.outputs.id}}"}, {"person_id": "alice"})
            is None
        )

    def test_blank_person_id_still_uses_the_pipeline_fallbacks(self):
        assert resolve_person_id({"person_id": "  "}, {"person_id": "alice"}) == "alice"


class _Surfaces:
    def __init__(self, result: str | None = None, error: Exception | None = None) -> None:
        self.result, self.error = result, error
        self.asked: list[str] = []

    async def surface_for_person(self, person_id: str) -> str | None:
        self.asked.append(person_id)
        if self.error is not None:
            raise self.error
        return self.result


class TestResolveSurfaceId:
    @pytest.mark.asyncio
    async def test_returns_the_surface_in_her_room(self):
        surfaces = _Surfaces("kitchen-tablet")
        services = SimpleNamespace(companion_surfaces=surfaces)

        assert await resolve_surface_id(services, "resident-1") == "kitchen-tablet"  # type: ignore[arg-type]
        assert surfaces.asked == ["resident-1"]

    @pytest.mark.asyncio
    async def test_no_person_or_registry_means_every_screen(self):
        surfaces = _Surfaces("kitchen-tablet")

        assert await resolve_surface_id(SimpleNamespace(companion_surfaces=surfaces), None) is None  # type: ignore[arg-type]
        assert await resolve_surface_id(SimpleNamespace(companion_surfaces=None), "r") is None  # type: ignore[arg-type]
        assert surfaces.asked == []

    @pytest.mark.asyncio
    async def test_a_lookup_failure_never_fails_the_step(self):
        services = SimpleNamespace(companion_surfaces=_Surfaces(error=RuntimeError("db down")))

        assert await resolve_surface_id(services, "resident-1") is None  # type: ignore[arg-type]
