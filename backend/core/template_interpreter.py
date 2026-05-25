"""Interpreter that walks the Lark AST and evaluates expressions against
pipeline_data dictionaries.

Reuses the existing resolve_path logic for path traversal and jmespath.search
for JMESPath queries.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jmespath  # type: ignore[import-untyped]

from backend.core.template import resolve_path
from backend.core.template_ast import (
    ASTNode,
    BinOp,
    Comparison,
    FuncCall,
    Literal,
    NotOp,
    PathNode,
    TemplateSyntaxError,
    parse_expression,
)


class TemplateTypeError(Exception):
    """Raised when an expression evaluates to a non-boolean in boolean context."""


def evaluate_expression(expr: str, pipeline_data: Mapping[str, Any]) -> Any:
    """Parse and evaluate an expression string."""
    ast = parse_expression(expr)
    return _eval(ast, pipeline_data)


def evaluate_condition(expr: str, pipeline_data: Mapping[str, Any]) -> bool:
    """Parse, evaluate, and coerce to bool."""
    result = evaluate_expression(expr, pipeline_data)
    if isinstance(result, bool):
        return result
    raise TemplateTypeError(f"Expected boolean result, got {type(result).__name__}: {result!r}")


# -- AST evaluation -----------------------------------------------------------


def _eval(node: ASTNode, data: Mapping[str, Any]) -> Any:
    if isinstance(node, PathNode):
        return _eval_path(node, data)
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, FuncCall):
        return _eval_func(node, data)
    if isinstance(node, Comparison):
        return _eval_comparison(node, data)
    if isinstance(node, NotOp):
        return not _eval(node.operand, data)
    if isinstance(node, BinOp):
        return _eval_binop(node, data)
    raise TemplateSyntaxError(f"Unknown AST node: {type(node).__name__}")


# -- Path evaluation ----------------------------------------------------------


def _eval_path(node: PathNode, data: Mapping[str, Any]) -> Any:
    """Resolve a PathNode against pipeline_data."""
    if not node.segments:
        if node.jmespath:
            return _eval_jmespath(node.jmespath, data)
        return None

    # Build dotted path from segments
    dotted = ".".join(node.segments)
    value = resolve_path(dotted, data)

    # Apply JMESPath filter if present
    if node.jmespath and value is not None:
        try:
            return jmespath.search(node.jmespath, value)
        except Exception:
            return None

    return value


def _eval_jmespath(expression: str, data: Any) -> Any:
    """Evaluate a raw JMESPath expression against data."""
    try:
        return jmespath.search(expression.strip(), data)
    except Exception:
        return None


# -- Function evaluation ------------------------------------------------------


_FUNCTIONS: dict[str, Any] = {}


def _register(name: str) -> Any:
    def decorator(fn: Any) -> Any:
        _FUNCTIONS[name] = fn
        return fn

    return decorator


@_register("contains")
def _fn_contains(haystack: Any, needle: Any) -> bool:
    if isinstance(haystack, str):
        return str(needle) in haystack
    if isinstance(haystack, (list, dict)):
        return needle in haystack
    return False


@_register("icontains")
def _fn_icontains(haystack: Any, needle: Any) -> bool:
    if isinstance(haystack, str):
        return str(needle).lower() in haystack.lower()
    return False


@_register("length")
def _fn_length(value: Any) -> int:
    if isinstance(value, (list, str, dict, tuple)):
        return len(value)
    return 0


@_register("lower")
def _fn_lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


@_register("upper")
def _fn_upper(value: Any) -> Any:
    return value.upper() if isinstance(value, str) else value


@_register("keys")
def _fn_keys(value: Any) -> Any:
    return list(value.keys()) if isinstance(value, dict) else []


@_register("values")
def _fn_values(value: Any) -> Any:
    return list(value.values()) if isinstance(value, dict) else []


@_register("exists")
def _fn_exists(value: Any) -> bool:
    return value is not None


def _eval_func(node: FuncCall, data: Mapping[str, Any]) -> Any:
    fn = _FUNCTIONS.get(node.name)
    if fn is None:
        raise TemplateSyntaxError(f"Unknown function: {node.name}")
    args = [_eval(arg, data) for arg in node.args]
    try:
        return fn(*args)
    except Exception as e:
        raise TemplateSyntaxError(f"Error calling {node.name}(...): {e}") from e


# -- Comparison / boolean evaluation ------------------------------------------


def _compare(left: Any, right: Any, op: str) -> bool:
    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
    except TypeError:
        return False
    return False


def _eval_comparison(node: Comparison, data: Mapping[str, Any]) -> Any:
    left = _eval(node.left, data)
    right = _eval(node.right, data)
    return _compare(left, right, node.op)


def _eval_binop(node: BinOp, data: Mapping[str, Any]) -> Any:
    left = _eval(node.left, data)
    if node.op == "and":
        if not left:
            # Short-circuit
            return left
        return _eval(node.right, data)
    if node.op == "or":
        if left:
            # Short-circuit
            return left
        return _eval(node.right, data)
    raise TemplateSyntaxError(f"Unknown binary operator: {node.op}")
