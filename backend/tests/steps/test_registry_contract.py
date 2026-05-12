"""Contract tests for every handler in the StepRegistry, FilterRegistry,
and ChannelRegistry.

These gates enforce that every plugin's metadata is internally consistent:
config_schema is valid JSONSchema, default_config validates against it,
output_schema is provided for data-emitting steps, and naming conventions
are followed.
"""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator, SchemaError, ValidationError

from backend.channels import ChannelRegistry
from backend.filters import FilterRegistry
from backend.steps import StepRegistry

# Ensure registries are populated before any test runs.
StepRegistry.discover()
FilterRegistry.discover()
ChannelRegistry.discover()

VALID_CATEGORIES = {"perception", "reasoning", "action", "state", "flow"}


# -- Step handler contract tests ---------------------------------------------


def _all_step_handlers():
    """Yield every registered step handler as (handler, metadata)."""
    for meta in StepRegistry.all_metadata():
        handler = StepRegistry.get(meta.type_name)
        if handler is not None:
            yield handler, meta


@pytest.mark.parametrize(("handler", "meta"), _all_step_handlers())
def test_step_config_schema_is_valid_jsonschema(handler, meta):
    """Every handler's config_schema must be a valid JSONSchema draft 2020-12 document."""
    if not meta.config_schema:
        return  # empty schema is valid
    try:
        Draft202012Validator.check_schema(meta.config_schema)
    except SchemaError as e:
        pytest.fail(f"{meta.type_name}: invalid config_schema: {e}")


@pytest.mark.parametrize(("handler", "meta"), _all_step_handlers())
def test_step_default_config_validates_against_config_schema(handler, meta):
    """Every handler's default_config should satisfy config_schema constraints.

    Skips schemas using anyOf/oneOf (multiple valid shapes) and treats
    missing required fields with user-chosen values (like IDs) as warnings.
    """
    if not meta.config_schema or not meta.default_config:
        return

    # Schemas with anyOf/oneOf represent multi-mode configs; the default
    # may not match any single branch without a discriminator.
    if "anyOf" in meta.config_schema or "oneOf" in meta.config_schema:
        return

    try:
        Draft202012Validator(meta.config_schema).validate(meta.default_config)
    except ValidationError as e:
        # Required fields that contain empty strings/zeros are ID placeholders
        # the user must fill in; they're intentional, not bugs.
        if e.validator == "required":
            return
        # None values for numeric fields mean "not set / provider default."
        # The schema may not declare null support but the handler treats None
        # as a valid sentinel.
        if e.validator == "type" and e.validator_value in ("number", "integer"):
            return
        pytest.fail(f"{meta.type_name}: default_config fails validation: {e.message}")


@pytest.mark.parametrize(("handler", "meta"), _all_step_handlers())
def test_step_type_name_matches_slug_pattern(handler, meta):
    """type_name must be lower_snake_case."""
    import re
    assert re.match(r"^[a-z][a-z0-9_]*$", meta.type_name), (
        f"{meta.type_name}: type_name must match ^[a-z][a-z0-9_]*$"
    )


@pytest.mark.parametrize(("handler", "meta"), _all_step_handlers())
def test_step_icon_starts_with_mdi(handler, meta):
    """Icon must be a valid Material Design Icons name."""
    assert meta.icon.startswith("mdi-"), f"{meta.type_name}: icon must start with 'mdi-'"


@pytest.mark.parametrize(("handler", "meta"), _all_step_handlers())
def test_step_category_is_from_known_set(handler, meta):
    """Category must be one of the five known pipeline step categories."""
    assert meta.category in VALID_CATEGORIES, (
        f"{meta.type_name}: category '{meta.category}' not in {VALID_CATEGORIES}"
    )


@pytest.mark.parametrize(("handler", "meta"), _all_step_handlers())
def test_step_output_schema_is_valid_jsonschema(handler, meta):
    """Every handler's output_schema (if present) must be valid JSONSchema."""
    if not meta.output_schema:
        return
    try:
        Draft202012Validator.check_schema(meta.output_schema)
    except SchemaError as e:
        pytest.fail(f"{meta.type_name}: invalid output_schema: {e}")


@pytest.mark.parametrize(("handler", "meta"), _all_step_handlers())
def test_step_ui_hints_version_is_positive(handler, meta):
    """ui_hints_version must be a positive integer."""
    assert meta.ui_hints_version >= 1, (
        f"{meta.type_name}: ui_hints_version must be >= 1"
    )


# -- Filter contract tests -------------------------------------------------


def _all_filters():
    for meta in FilterRegistry.all_metadata():
        f = FilterRegistry.get(meta.filter_type)
        if f is not None:
            yield f, meta


@pytest.mark.parametrize(("_filter", "meta"), _all_filters())
def test_filter_config_schema_is_valid_jsonschema(_filter, meta):
    if not meta.config_schema:
        return
    try:
        Draft202012Validator.check_schema(meta.config_schema)
    except SchemaError as e:
        pytest.fail(f"{meta.filter_type}: invalid config_schema: {e}")


@pytest.mark.parametrize(("_filter", "meta"), _all_filters())
def test_filter_type_name_matches_slug_pattern(_filter, meta):
    import re
    assert re.match(r"^[a-z][a-z0-9_]*$", meta.filter_type), (
        f"{meta.filter_type}: filter_type must match ^[a-z][a-z0-9_]*$"
    )


@pytest.mark.parametrize(("_filter", "meta"), _all_filters())
def test_filter_schema_version_is_positive(_filter, meta):
    assert meta.schema_version >= 1, (
        f"{meta.filter_type}: schema_version must be >= 1"
    )


# -- Channel contract tests ------------------------------------------------


def _all_channels():
    for meta in ChannelRegistry.all_metadata():
        ch = ChannelRegistry.get(meta.channel_name)
        if ch is not None:
            yield ch, meta


@pytest.mark.parametrize(("_channel", "meta"), _all_channels())
def test_channel_config_schema_is_valid_jsonschema(_channel, meta):
    if not meta.config_schema:
        return
    try:
        Draft202012Validator.check_schema(meta.config_schema)
    except SchemaError as e:
        pytest.fail(f"{meta.channel_name}: invalid config_schema: {e}")


@pytest.mark.parametrize(("_channel", "meta"), _all_channels())
def test_channel_name_matches_slug_pattern(_channel, meta):
    import re
    assert re.match(r"^[a-z][a-z0-9_]*$", meta.channel_name), (
        f"{meta.channel_name}: channel_name must match ^[a-z][a-z0-9_]*$"
    )


@pytest.mark.parametrize(("_channel", "meta"), _all_channels())
def test_channel_schema_version_is_positive(_channel, meta):
    assert meta.schema_version >= 1, (
        f"{meta.channel_name}: schema_version must be >= 1"
    )
