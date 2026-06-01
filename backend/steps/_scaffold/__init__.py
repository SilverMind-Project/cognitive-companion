"""Scaffolding CLI for generating new step handler boilerplate."""

from __future__ import annotations

import sys
from string import Template

VALID_CATEGORIES = {"perception", "reasoning", "action", "state", "flow"}

_HANDLER_TEMPLATE = Template('''"""$display_name step handler."""

from backend.steps import StepRegistry
from backend.steps.base import StepHandler, StepMetadata, StepResult


@StepRegistry.register
class ${class_name}(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="${type_name}",
            display_name="$display_name",
            category="$category",
            icon="mdi-star",
            description="TODO: describe what this step does.",
            config_schema={
                "type": "object",
                "properties": {
                    "output_key": {
                        "type": "string",
                        "default": "${type_name}_response",
                        "x-ui": {"widget": "text", "section": "advanced"},
                    },
                },
            },
            default_config={"output_key": "${type_name}_response"},
            output_schema={
                "type": "object",
                "properties": {
                    "${type_name}_response": {
                        "type": "string",
                        "description": "TODO: document this output",
                    },
                },
            },
        )

    async def execute(self, step, execution, pipeline_data, trigger, services) -> StepResult:
        config = step.config_json or {}
        output_key = config.get("output_key", "${type_name}_response")
        # TODO: implement step logic
        return StepResult(data={output_key: None})
''')

_TEST_TEMPLATE = Template('''"""Tests for ${type_name} step handler."""

from dataclasses import dataclass

from backend.steps import StepRegistry
from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import StepResult, TriggerContext


@dataclass
class _FakeStep:
    id: int = 1
    step_type: str = "${type_name}"
    label: str = "${type_name}_1"
    config_json: dict | None = None
    order: int = 0
    enabled: bool = True


@dataclass
class _FakeExecution:
    id: int = 1
    status: str = "running"
    pipeline_data_json: dict | None = None
    current_step_id: int | None = None
    error: str | None = None


def _make_trigger() -> TriggerContext:
    return TriggerContext(trigger_type="manual")


async def test_metadata_conforms():
    """Generated contract test."""
    handler = StepRegistry.get("${type_name}")
    assert handler is not None
    meta = handler.metadata()
    assert meta.type_name == "${type_name}"
    assert meta.category in ("perception", "reasoning", "action", "state", "flow")
    assert meta.icon.startswith("mdi-")
    assert meta.schema_version >= 1


async def test_execute_emits_output_key():
    """Generated smoke test -- replace with real assertions."""
    handler = StepRegistry.get("${type_name}")
    assert handler is not None
    step = _FakeStep()
    exec_ = _FakeExecution()
    result = await handler.execute(step, exec_, {}, _make_trigger(), MagicMock())
    assert isinstance(result, StepResult)
    assert result.success
    assert "${type_name}_response" in result.data
    assert_output_conforms_to_schema(handler, result)
''')


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 3 or args[0] != "new":
        print("Usage: python -m backend.steps._scaffold new <type_name> --category <category>")
        print("  type_name: lower_snake_case, e.g. 'my_step'")
        print("  category: perception | reasoning | action | state | flow")
        sys.exit(1)

    type_name = args[1]
    category = "action"
    if "--category" in args:
        idx = args.index("--category")
        if idx + 1 < len(args):
            category = args[idx + 1]

    if category not in VALID_CATEGORIES:
        print(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")
        sys.exit(1)

    # Generate class name
    class_name = "".join(part.title() for part in type_name.split("_")) + "Handler"

    # Generate display name
    display_name = " ".join(part.title() for part in type_name.split("_"))

    # Write handler file
    handler_path = f"backend/steps/builtin/{type_name}.py"
    with open(handler_path, "w") as f:
        f.write(
            _HANDLER_TEMPLATE.substitute(
                type_name=type_name,
                class_name=class_name,
                display_name=display_name,
                category=category,
            )
        )
    print(f"Created {handler_path}")

    # Write test file
    test_path = f"backend/tests/steps/test_{type_name}.py"
    with open(test_path, "w") as f:
        f.write(
            _TEST_TEMPLATE.substitute(
                type_name=type_name,
                test_class_name="".join(part.title() for part in type_name.split("_")) + "Test",
            )
        )
    print(f"Created {test_path}")

    print("\nNext steps:")
    print(f"  1. Implement {class_name}.execute() in {handler_path}")
    print(f"  2. Update tests in {test_path}")
    print(f"  3. Run: uv run --project backend pytest {test_path}")


if __name__ == "__main__":
    main()
