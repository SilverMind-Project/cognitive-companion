"""Test helpers for step handler validation.

These are intended for use in test files, not in production code.
"""

from __future__ import annotations

from backend.steps.base import StepHandler, StepResult


def assert_output_conforms_to_schema(handler: StepHandler, result: StepResult) -> None:
    """Assert that a step's output contains all keys declared in its output_schema.

    Only checks keys declared in schema.properties. Extra keys in result.data
    are allowed (steps may emit debugging info). Only validates presence, not
    types (full JSONSchema validation is done at the contract test level).
    """
    schema = handler.metadata().output_schema
    if not schema:
        return
    for key in schema.get("properties", {}):
        assert key in result.data, (
            f"{handler.metadata().type_name} declared output key '{key}' "
            f"in output_schema but did not emit it. Emitted keys: {list(result.data.keys())}"
        )
