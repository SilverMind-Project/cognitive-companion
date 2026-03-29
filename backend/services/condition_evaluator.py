"""Safe expression evaluator for pipeline condition steps.

Implements a recursive-descent parser that evaluates expressions against
pipeline data dictionaries.  This intentionally avoids ``eval()`` to prevent
code injection.

Supported syntax
----------------
- Path access: ``person_detections.count``, ``logic_response.is_notification_needed``
- Literals: integers, floats, ``true``, ``false``, ``null``, quoted strings
- Comparisons: ``==``, ``!=``, ``>``, ``<``, ``>=``, ``<=``
- Boolean operators: ``and``, ``or``, ``not``
- Functions: ``exists(path)``, ``contains(path, value)``
- Parenthesised sub-expressions: ``(expr)``

Examples::

    person_detections.count > 0
    logic_response.is_notification_needed == true
    exists(translation) and not contains(vision_response, "empty")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_SPEC = [
    ("NUMBER", r"-?\d+(?:\.\d+)?"),
    ("STRING", r'"[^"]*"|\'[^\']*\''),
    ("BOOL", r"\b(?:true|false)\b"),
    ("NULL", r"\bnull\b"),
    ("CMP", r"==|!=|>=|<=|>|<"),
    ("AND", r"\band\b"),
    ("OR", r"\bor\b"),
    ("NOT", r"\bnot\b"),
    ("FUNC", r"\b(?:exists|contains)\b"),
    ("IDENT", r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("COMMA", r","),
    ("WS", r"\s+"),
]

_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))


@dataclass
class _Token:
    kind: str
    value: str
    pos: int


def _tokenise(expression: str) -> list[_Token]:
    tokens: list[_Token] = []
    for m in _TOKEN_RE.finditer(expression):
        kind = m.lastgroup
        if kind == "WS":
            continue
        tokens.append(_Token(kind=kind, value=m.group(), pos=m.start()))  # type: ignore[arg-type]
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser / evaluator
# ---------------------------------------------------------------------------


class ConditionEvaluator:
    """Evaluate a condition expression against a ``pipeline_data`` dict."""

    def evaluate(self, expression: str, data: dict[str, Any]) -> bool:
        """Return *True* if *expression* holds for *data*.

        Malformed expressions log a warning and return *False*.
        """
        try:
            tokens = _tokenise(expression)
            result, _pos = self._parse_or(tokens, 0, data)
            return bool(result)
        except Exception:
            logger.warning("condition_eval_failed", expression=expression)
            return False

    # -- grammar rules (precedence: or < and < not < comparison < atom) ----

    def _parse_or(
        self, tokens: list[_Token], pos: int, data: dict
    ) -> tuple[Any, int]:
        left, pos = self._parse_and(tokens, pos, data)
        while pos < len(tokens) and tokens[pos].kind == "OR":
            pos += 1  # consume 'or'
            right, pos = self._parse_and(tokens, pos, data)
            left = left or right
        return left, pos

    def _parse_and(
        self, tokens: list[_Token], pos: int, data: dict
    ) -> tuple[Any, int]:
        left, pos = self._parse_not(tokens, pos, data)
        while pos < len(tokens) and tokens[pos].kind == "AND":
            pos += 1  # consume 'and'
            right, pos = self._parse_not(tokens, pos, data)
            left = left and right
        return left, pos

    def _parse_not(
        self, tokens: list[_Token], pos: int, data: dict
    ) -> tuple[Any, int]:
        if pos < len(tokens) and tokens[pos].kind == "NOT":
            pos += 1
            value, pos = self._parse_not(tokens, pos, data)
            return not value, pos
        return self._parse_comparison(tokens, pos, data)

    def _parse_comparison(
        self, tokens: list[_Token], pos: int, data: dict
    ) -> tuple[Any, int]:
        left, pos = self._parse_atom(tokens, pos, data)
        if pos < len(tokens) and tokens[pos].kind == "CMP":
            op = tokens[pos].value
            pos += 1
            right, pos = self._parse_atom(tokens, pos, data)
            return _compare(left, right, op), pos
        return left, pos

    def _parse_atom(
        self, tokens: list[_Token], pos: int, data: dict
    ) -> tuple[Any, int]:
        if pos >= len(tokens):
            return None, pos

        tok = tokens[pos]

        # Parenthesised sub-expression
        if tok.kind == "LPAREN":
            pos += 1
            value, pos = self._parse_or(tokens, pos, data)
            if pos < len(tokens) and tokens[pos].kind == "RPAREN":
                pos += 1
            return value, pos

        # Function call
        if tok.kind == "FUNC":
            return self._parse_function(tokens, pos, data)

        # Literal values
        if tok.kind == "NUMBER":
            val = float(tok.value) if "." in tok.value else int(tok.value)
            return val, pos + 1

        if tok.kind == "STRING":
            return tok.value[1:-1], pos + 1  # strip quotes

        if tok.kind == "BOOL":
            return tok.value == "true", pos + 1

        if tok.kind == "NULL":
            return None, pos + 1

        # Path lookup against pipeline data
        if tok.kind == "IDENT":
            return _resolve_path(data, tok.value), pos + 1

        # Unknown token — skip
        return None, pos + 1

    def _parse_function(
        self, tokens: list[_Token], pos: int, data: dict
    ) -> tuple[Any, int]:
        func_name = tokens[pos].value
        pos += 1  # consume function name

        # Expect '('
        if pos < len(tokens) and tokens[pos].kind == "LPAREN":
            pos += 1
        else:
            return False, pos

        args: list[Any] = []
        while pos < len(tokens) and tokens[pos].kind != "RPAREN":
            if tokens[pos].kind == "COMMA":
                pos += 1
                continue
            # Arguments are either path identifiers or literal values
            val, pos = self._parse_atom(tokens, pos, data)
            args.append(val)

        # Consume ')'
        if pos < len(tokens) and tokens[pos].kind == "RPAREN":
            pos += 1

        if func_name == "exists":
            # exists(path) — check if path resolves to a non-None value
            # Re-resolve: the arg was already resolved, so check truthiness
            return args[0] is not None if args else False, pos

        if func_name == "contains":
            # contains(path_value, search_value)
            if len(args) >= 2:
                haystack = args[0]
                needle = args[1]
                if isinstance(haystack, str):
                    return str(needle) in haystack, pos
                if isinstance(haystack, (list, dict)):
                    return needle in haystack, pos
            return False, pos

        return False, pos


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(data: dict, path: str) -> Any:
    """Resolve a dotted path like ``person_detections.count`` against *data*.

    Supports both nested dict access and special ``count`` / ``length``
    accessors on list values.
    """
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part in ("count", "length", "len"):
            return len(current)
        else:
            return None
        if current is None:
            return None
    return current


def _compare(left: Any, right: Any, op: str) -> bool:
    """Compare two values with the given operator."""
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
