"""Template expression validator for pipeline step configs.

Extracts ``{{ }}`` expressions from config fields, parses them with
the Lark grammar, and validates that referenced step labels and paths
exist against the current rule context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.core.template_ast import TemplateSyntaxError, extract_expressions, parse_expression
from backend.steps import StepRegistry


@dataclass(frozen=True)
class TemplateError:
    """A single template validation error."""

    field_path: str
    position: tuple[int, int] | None = None
    severity: Literal["error", "warning"] = "error"
    code: str = ""
    message: str = ""
    suggestion: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "field_path": self.field_path,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.position:
            d["position"] = list(self.position)
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


def validate_step_config(
    step_type: str,
    config: dict,
    known_labels: list[str],
    *,
    step_registry: type[StepRegistry] | None = None,
) -> list[TemplateError]:
    """Validate every template-bearing field in a step config.

    Returns a list of ``TemplateError``; empty list means all expressions
    are valid.
    """
    if step_registry is None:
        step_registry = StepRegistry
    step_registry.discover()

    errors: list[TemplateError] = []

    for _field_name, errors_for_field in _validate_fields(step_type, config, known_labels, step_registry):
        errors.extend(errors_for_field)

    return errors


def _validate_fields(
    step_type: str,
    config: dict,
    known_labels: list[str],
    step_registry: type[StepRegistry],
):
    """Yield (field_name, [TemplateError]) for each template-bearing field."""
    template_fields = _get_template_fields(step_type, step_registry)
    field_errors: list[TemplateError] = []

    for field_name in template_fields:
        value = config.get(field_name)
        if not isinstance(value, str) or not value.strip():
            continue

        try:
            expressions = extract_expressions(value)
        except Exception:
            continue

        for expr_body, start, end in expressions:
            try:
                ast = parse_expression(expr_body)
            except TemplateSyntaxError as e:
                field_errors.append(
                    TemplateError(
                        field_path=field_name,
                        position=(start, end),
                        severity="error",
                        code="parse_error",
                        message=str(e),
                    )
                )
                continue

            _validate_ast_labels(
                ast,
                field_name,
                (start, end),
                known_labels,
                field_errors,
            )

    return [(None, field_errors)] if field_errors else []


def _get_template_fields(step_type: str, step_registry: type[StepRegistry]) -> list[str]:
    """Return field names in the step config that support templates."""
    fields: list[str] = []
    for meta in step_registry.all_metadata():
        if meta.type_name == step_type:
            props = meta.config_schema.get("properties", {})
            for field_name, prop_schema in props.items():
                # Fields with x-ui.supports_template
                ui_hints = prop_schema.get("x-ui", {})
                if ui_hints.get("supports_template") or ui_hints.get("widget") in (
                    "template-textarea",
                    "template-text",
                ):
                    fields.append(field_name)
                    continue
                # Fallback: fields named 'expression', 'prompt', 'message'
                if field_name in ("expression", "prompt", "message"):
                    fields.append(field_name)
            break
    return fields


def _validate_ast_labels(
    node,
    field_name: str,
    position: tuple[int, int],
    known_labels: list[str],
    errors: list[TemplateError],
) -> None:
    """Recursively walk AST looking for unknown step labels."""
    from backend.core.template_ast import FuncCall, PathNode

    if isinstance(node, PathNode):
        segments = node.segments
        if segments and segments[0] == "steps" and len(segments) > 1:
            label = segments[1]
            if label not in known_labels:
                suggestion = _suggest_label(label, known_labels)
                errors.append(
                    TemplateError(
                        field_path=field_name,
                        position=position,
                        severity="warning",
                        code="unknown_label",
                        message=f"Unknown step label '{label}' in template expression",
                        suggestion=suggestion,
                    )
                )
    elif isinstance(node, FuncCall):
        for arg in node.args:
            _validate_ast_labels(arg, field_name, position, known_labels, errors)

    # Recurse into children via common attributes
    for attr in ("left", "right", "operand"):
        child = getattr(node, attr, None)
        if child is not None:
            _validate_ast_labels(child, field_name, position, known_labels, errors)


def _suggest_label(label: str, known_labels: list[str]) -> str | None:
    """Suggest the closest matching known label using difflib."""
    import difflib

    matches = difflib.get_close_matches(label, known_labels, n=1, cutoff=0.6)
    if matches:
        return f"Did you mean '{matches[0]}'?"
    return None
