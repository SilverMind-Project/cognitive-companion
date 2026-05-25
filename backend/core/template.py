"""Template renderer and expression evaluator for pipeline step prompts.

Resolves ``{{ expr }}`` expressions against *pipeline_data* using a Lark-based
grammar. The grammar supports dotted paths, JMESPath pipes, comparisons,
boolean combinators, and built-in functions.

Simple ``{{path.to.value}}`` references use fast regex + resolve_path for
substitution; full expressions with operators, functions, or pipes use the
Lark parser.

``resolve_path`` remains the fast path for dotted traversal with JSON
auto-parsing and list-index support.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

__all__ = ["evaluate_condition", "evaluate_expression", "render_template", "resolve_path"]

# Matches {{ expr }} with optional whitespace inside braces.
_VAR_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")

# Operators/functions/pipe that indicate a full grammar parse is needed
_SIMPLE_PATH_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$")


def _try_parse_json(value: Any) -> Any:
    """If *value* is a JSON-encoded string, return the parsed object."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped and stripped[0] in ("{", "["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError, ValueError:
            pass
    return value


def resolve_path(path: str, data: Mapping[str, Any] | Any) -> Any:
    """Walk *data* following a dotted *path*.

    Numeric segments are treated as list indices. JSON string auto-parsing
    is applied after the first segment.

    Returns ``None`` when any segment fails to resolve.
    """
    current: Any = data
    segments = path.split(".")
    for i, segment in enumerate(segments):
        if current is None:
            return None
        if i > 0 and isinstance(current, str):
            current = _try_parse_json(current)
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(segment)]
            except ValueError, IndexError:
                return None
        else:
            current = getattr(current, segment, None)
    return current


def _is_simple_path(expr: str) -> bool:
    """Return True if *expr* is a plain dotted identifier path.

    Excludes keywords and literals that would match the same pattern.
    """
    if not _SIMPLE_PATH_RE.match(expr):
        return False
    # Exclude language keywords
    return expr not in ("true", "false", "null", "and", "or", "not")


def evaluate_expression(expr: str, pipeline_data: Mapping[str, Any]) -> Any:
    """Parse and evaluate a single ``{{ }}`` expression.

    For simple dotted paths, uses the fast resolve_path. For expressions
    with operators, functions, or pipes, uses the Lark grammar.
    """
    expr = expr.strip()
    if _is_simple_path(expr):
        return resolve_path(expr, pipeline_data)

    from backend.core.template_ast import parse_expression
    from backend.core.template_interpreter import _eval

    ast = parse_expression(expr)
    return _eval(ast, pipeline_data)


def evaluate_condition(expr: str, pipeline_data: Mapping[str, Any]) -> bool:
    """Evaluate an expression and coerce to bool.

    Raises TemplateTypeError if the expression does not evaluate to boolean.
    """
    from backend.core.template_interpreter import TemplateTypeError

    result = evaluate_expression(expr, pipeline_data)
    if isinstance(result, bool):
        return result
    raise TemplateTypeError(f"Expected boolean result, got {type(result).__name__}: {result!r}")


def render_template(
    template: str,
    pipeline_data: Mapping[str, Any],
    trigger_vars: Mapping[str, Any] | None = None,
) -> str:
    """Replace ``{{ expr }}`` placeholders in *template* with evaluated values.

    Simple path references use fast resolve_path. Complex expressions use
    the Lark grammar. Unresolvable placeholders are left as-is.
    """
    if "{{" not in template:
        return template

    merged: dict[str, Any] = dict(pipeline_data)
    if trigger_vars:
        merged["trigger"] = dict(trigger_vars)
        for k, v in trigger_vars.items():
            merged.setdefault(k, v)

    def _replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        try:
            value = evaluate_expression(expr, merged)
        except Exception:
            return match.group(0)  # leave unresolved

        if value is None:
            return match.group(0)
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    return _VAR_RE.sub(_replace, template)
