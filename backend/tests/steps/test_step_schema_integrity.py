"""Meta-tests: every registered step/filter schema is well-formed and self-consistent.

These guard the write-time validation added for hardening finding C7
(`backend/services/step_config_validation.py`): a malformed `config_schema` or a
`default_config` that does not satisfy its own schema is a defect in the step/filter
definition, caught here at test time rather than surfacing as every save failing.
"""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from backend.filters import FilterRegistry
from backend.steps import StepRegistry


def _all_step_metadata():
    StepRegistry.discover()
    return StepRegistry.all_metadata()


def _all_filter_metadata():
    FilterRegistry.discover()
    return FilterRegistry.all_metadata()


@pytest.mark.parametrize("meta", _all_step_metadata(), ids=lambda m: m.type_name)
def test_step_config_schema_is_well_formed(meta):
    try:
        Draft202012Validator.check_schema(meta.config_schema)
    except SchemaError as e:
        pytest.fail(f"Step '{meta.type_name}' config_schema is not valid JSONSchema: {e}")


@pytest.mark.parametrize("meta", _all_step_metadata(), ids=lambda m: m.type_name)
def test_step_output_schema_is_well_formed(meta):
    if not meta.output_schema:
        pytest.skip(f"Step '{meta.type_name}' declares no output_schema")
    try:
        Draft202012Validator.check_schema(meta.output_schema)
    except SchemaError as e:
        pytest.fail(f"Step '{meta.type_name}' output_schema is not valid JSONSchema: {e}")


# Steps whose default_config is intentionally incomplete: the omitted field(s) identify a
# specific admin-created object (a routine, quiz, or info card) that has no sensible default
# value, or (interactive_prompt) require the author to choose one of two mutually exclusive
# template fields. default_config is a starting template for a new step on the canvas, not a
# submittable config; the identifying field is filled in via the step's config dialog before
# the step is saved with real content. For these types the meta-test checks only that whatever
# keys ARE present in default_config satisfy their declared type/enum (catches typos and drift)
# without demanding the schema's completeness constraints (`required`, `anyOf`).
_COMPLETENESS_EXEMPT_STEPS: dict[str, str] = {
    "guided_task_start": "routine_id has no sensible default; chosen via the step config dialog",
    "quiz_start": "quiz_id has no sensible default; chosen via the step config dialog",
    "info_card": "info_card_id has no sensible default; chosen via the step config dialog",
    "interactive_prompt": (
        "anyOf requires one of voice_prompt_template/popup_message_template; "
        "neither has a sensible default text"
    ),
}


def _schema_without_completeness_constraints(schema: dict) -> dict:
    return {k: v for k, v in schema.items() if k not in ("required", "anyOf", "oneOf")}


@pytest.mark.parametrize("meta", _all_step_metadata(), ids=lambda m: m.type_name)
def test_step_default_config_matches_own_schema(meta):
    if meta.type_name in _COMPLETENESS_EXEMPT_STEPS:
        schema = _schema_without_completeness_constraints(meta.config_schema)
    else:
        schema = meta.config_schema
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(meta.default_config), key=lambda e: list(e.path))
    assert not errors, (
        f"Step '{meta.type_name}' default_config violates its own config_schema: "
        + "; ".join(f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors)
    )


@pytest.mark.parametrize("meta", _all_filter_metadata(), ids=lambda m: m.filter_type)
def test_filter_config_schema_is_well_formed(meta):
    try:
        Draft202012Validator.check_schema(meta.config_schema)
    except SchemaError as e:
        pytest.fail(f"Filter '{meta.filter_type}' config_schema is not valid JSONSchema: {e}")


@pytest.mark.parametrize("meta", _all_step_metadata(), ids=lambda m: m.type_name)
def test_step_config_vocabulary_m34_guard(meta):
    """M34 guard: Prevent cts_window or cts_frames_path from returning."""
    schema = meta.config_schema
    if "properties" in schema:
        assert "cts_frames_path" not in schema["properties"], (
            f"Step '{meta.type_name}' includes forbidden property cts_frames_path"
        )
        if "image_source" in schema["properties"]:
            enum = schema["properties"]["image_source"].get("enum", [])
            assert "cts_window" not in enum, (
                f"Step '{meta.type_name}' image_source enum includes forbidden member cts_window"
            )
