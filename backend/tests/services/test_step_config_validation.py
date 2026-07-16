from __future__ import annotations

from backend.services.step_config_validation import validate_step_config_schema
from backend.steps import StepRegistry

StepRegistry.discover()


def test_empty_config_is_not_validated():
    assert validate_step_config_schema("wait", {}) == []
    assert validate_step_config_schema("quiz_start", {}) == []


def test_unknown_step_type_is_not_validated():
    assert validate_step_config_schema("not_a_real_step_type", {"anything": True}) == []


def test_invalid_config_is_rejected():
    errors = validate_step_config_schema("wait", {"minutes": "not-a-number"})
    assert errors
    assert any("minutes" in e for e in errors)


def test_valid_config_passes():
    assert validate_step_config_schema("wait", {"minutes": 10}) == []


def test_none_values_are_treated_as_absent():
    """A cleared Vuetify combobox emits null for an optional field; that must not 422."""
    errors = validate_step_config_schema(
        "presence_query", {"signal_kind": None, "person_id": None, "output_key": "presence"}
    )
    assert errors == []


def test_config_with_only_none_values_is_treated_as_empty():
    assert validate_step_config_schema("presence_query", {"signal_kind": None}) == []


def test_signal_kind_typo_is_still_rejected_alongside_none_values():
    errors = validate_step_config_schema(
        "presence_query", {"signal_kind": "gait_slowng", "person_id": None}
    )
    assert errors
    assert any("signal_kind" in e for e in errors)
