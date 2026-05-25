"""Lark-based expression parser for {{ }} template expressions.

Produces an AST that the interpreter walks for evaluation, and that
the validator walks for static analysis (path existence, type checking).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lark import Lark, Token, Tree

_GRAMMAR_PATH = Path(__file__).parent / "template_grammar.lark"
_PARSER = Lark.open(str(_GRAMMAR_PATH), parser="lalr", propagate_positions=True)

# Regex to extract {{ expr }} from template strings
_EXPR_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")


# -- AST nodes ---------------------------------------------------------------


class ASTNode:
    """Base class for all AST nodes."""


@dataclass(frozen=True)
class PathNode(ASTNode):
    segments: tuple[str, ...]  # e.g. ("steps", "scene_1", "outputs", "count")
    jmespath: str | None = None  # raw JMESPath after |


@dataclass(frozen=True)
class FuncCall(ASTNode):
    name: str
    args: tuple[ASTNode, ...]


@dataclass(frozen=True)
class Literal(ASTNode):
    kind: str  # string, number, boolean, null
    value: Any


@dataclass(frozen=True)
class Comparison(ASTNode):
    op: str  # ==, !=, >, <, >=, <=
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True)
class NotOp(ASTNode):
    operand: ASTNode


@dataclass(frozen=True)
class BinOp(ASTNode):
    op: str  # and, or
    left: ASTNode
    right: ASTNode


# -- Parser ------------------------------------------------------------------


class TemplateSyntaxError(Exception):
    """Raised when an expression cannot be parsed."""

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.position = position


def parse_expression(expr: str) -> ASTNode:
    """Parse a single expression string (the content inside {{ }}) into an AST.

    Raises TemplateSyntaxError on parse failure.
    """
    try:
        tree = _PARSER.parse(expr.strip())
    except Exception as e:
        raise TemplateSyntaxError(str(e)) from e
    return _transform(tree)


def extract_expressions(template: str) -> list[tuple[str, int, int]]:
    """Find all {{ expr }} in a template string.

    Returns list of (expression_body, start_pos, end_pos) tuples.
    """
    results: list[tuple[str, int, int]] = []
    for m in _EXPR_RE.finditer(template):
        results.append((m.group(1).strip(), m.start(), m.end()))
    return results


# -- AST transformer ---------------------------------------------------------


def _transform(tree: Tree) -> ASTNode:
    """Convert a Lark parse tree into our AST node types."""
    if tree.data == "path":
        return _transform_path(tree)
    if tree.data == "func_call":
        return _transform_func_call(tree)
    if tree.data in ("string", "number", "boolean", "null"):
        return _transform_literal(tree)
    if tree.data == "comparison":
        return _transform_comparison(tree)
    if tree.data == "not_op":
        return NotOp(operand=_transform(tree.children[0]))
    if tree.data in ("or_expr", "and_expr"):
        return _transform_binop(tree)
    # Fallback: recurse into the only child
    if len(tree.children) == 1:
        return _transform(tree.children[0])
    raise TemplateSyntaxError(f"Unexpected tree structure: {tree.data}")


def _transform_path(tree: Tree) -> PathNode:
    segments: list[str] = []
    jmespath: str | None = None
    _collect_path_parts(tree, segments)
    # Search for JMESPATH token anywhere in the path tree children
    jmespath = _find_jmespath(tree)
    return PathNode(segments=tuple(segments), jmespath=jmespath)


def _collect_path_parts(tree: Tree, segments: list[str]) -> None:
    """Recursively collect NAME and INT tokens from nested path trees."""
    for child in tree.children:
        if isinstance(child, Token):
            if child.type in ("NAME", "INT"):
                segments.append(child.value)
        elif isinstance(child, Tree) and child.data == "path":
            _collect_path_parts(child, segments)


def _find_jmespath(tree: Tree) -> str | None:
    """Find the first JMESPATH token in the tree (recursively)."""
    for child in tree.children:
        if isinstance(child, Token) and child.type == "JMESPATH":
            return child.value.strip()
        if isinstance(child, Tree):
            result = _find_jmespath(child)
            if result is not None:
                return result
    return None


def _transform_func_call(tree: Tree) -> FuncCall:
    # Unwrap nested func_call nodes that Lark produces
    children = list(tree.children)
    while len(children) == 1 and isinstance(children[0], Tree) and children[0].data == "func_call":
        children = list(children[0].children)

    name_token = children[0]
    if not isinstance(name_token, Token):
        raise TemplateSyntaxError(f"Expected function name token, got {type(name_token)}")
    name = name_token.value

    args: list[ASTNode] = []
    for child in children[1:]:
        if isinstance(child, Tree):
            args.append(_transform(child))
    return FuncCall(name=name, args=tuple(args))


def _transform_literal(tree: Tree) -> Literal:
    token = tree.children[0]
    if not isinstance(token, Token):
        raise TemplateSyntaxError(f"Expected literal token, got {type(token)}")
    kind = tree.data
    if kind == "string":
        return Literal(kind="string", value=token.value[1:-1])  # strip quotes
    if kind == "number":
        return Literal(
            kind="number", value=float(token.value) if "." in token.value else int(token.value)
        )
    if kind == "boolean":
        return Literal(kind="boolean", value=token.value == "true")
    if kind == "null":
        return Literal(kind="null", value=None)
    raise TemplateSyntaxError(f"Unknown literal kind: {kind}")


def _transform_comparison(tree: Tree) -> Comparison:
    op_token = None
    left_parts: list[Tree] = []
    right_parts: list[Tree] = []
    found_op = False
    for child in tree.children:
        if isinstance(child, Token) and child.type == "COMP_OP":
            op_token = child
            found_op = True
        elif not found_op:
            if isinstance(child, Tree):
                left_parts.append(child)
        else:
            if isinstance(child, Tree):
                right_parts.append(child)
    left = _transform(left_parts[0]) if left_parts else Literal("null", None)
    right = _transform(right_parts[0]) if right_parts else Literal("null", None)
    return Comparison(op=op_token.value if op_token else "==", left=left, right=right)


def _transform_binop(tree: Tree) -> ASTNode:
    op = "or" if tree.data == "or_expr" else "and"
    if len(tree.children) == 1:
        return _transform(tree.children[0])
    result = _transform(tree.children[0])
    i = 1
    while i < len(tree.children):
        next_node = _transform(tree.children[i])
        result = BinOp(op=op, left=result, right=next_node)
        i += 1
    return result
