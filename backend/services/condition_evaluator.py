"""Safe expression evaluator for pipeline condition steps.

Implements a recursive-descent parser that evaluates expressions against
pipeline data dictionaries.  This intentionally avoids ``eval()`` to prevent
code injection.

Supported syntax
----------------
- Path access: ``steps.scene_analysis_1.outputs.count``
- Literals: integers, floats, ``true``, ``false``, ``null``, quoted strings
- Comparisons: ``==``, ``!=``, ``>``, ``<``, ``>=``, ``<=``
- Boolean operators: ``and``, ``or``, ``not``
- Parenthesised sub-expressions: ``(expr)``

Built-in functions
------------------
- ``exists(path)`` -- true if the path resolves to a non-None value
- ``contains(path, value)`` -- substring / membership test (case-sensitive)
- ``icontains(path, value)`` -- case-insensitive substring test
- ``lower(path)`` -- returns the string value at path in lowercase
- ``upper(path)`` -- returns the string value at path in uppercase
- ``jq(expr)`` -- evaluate a JMESPath expression against the full pipeline
  data and return the result; supports custom functions ``lower()``,
  ``upper()``, and ``icontains()`` inside filter projections

JMESPath examples (inside ``jq()``)
-------------------------------------
- Filter an array: ``jq("steps.sa.outputs.scene_detections[?label == 'person']")``
- Case-insensitive label filter:
  ``jq("length(steps.sa.outputs.scene_detections[?contains(lower(label), 'person')])")``
- Confidence threshold (backtick = JMESPath JSON literal):
  jq("steps.sa.outputs.scene_detections[?confidence > `0.9`]")
- Count and compare (outer grammar):
  jq("length(steps.sa.outputs.scene_detections[?label == 'person'])") > 0
- Per-image description:
  jq("contains(lower(steps.scene_analysis_1.outputs.scene_images[0].scene_description), 'kitchen')")
- Per-image detection filter:
  jq("length(steps.scene_analysis_1.outputs.scene_images[1].scene_detections[?label == 'person'])") > 0
- Cross-all-images flatten + filter:
  jq("length(steps.scene_analysis_1.outputs.scene_images[].scene_detections[] | [?label == 'person'])") > 0
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import jmespath
from jmespath import functions as _jmespath_fn

from backend.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# JMESPath custom functions  (usable inside jq() filter projections)
# ---------------------------------------------------------------------------


class _CustomFunctions(_jmespath_fn.Functions):
    @_jmespath_fn.signature({"types": ["string"]})
    def _func_lower(self, s: str) -> str:
        return s.lower()

    @_jmespath_fn.signature({"types": ["string"]})
    def _func_upper(self, s: str) -> str:
        return s.upper()

    @_jmespath_fn.signature({"types": ["string"]}, {"types": ["string"]})
    def _func_icontains(self, subject: str, search: str) -> bool:
        return search.lower() in subject.lower()


_JMESPATH_OPTIONS = jmespath.Options(custom_functions=_CustomFunctions())


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
    ("FUNC", r"\b(?:exists|contains|icontains|jq|lower|upper)\b"),
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
    """Evaluate a condition expression against a ``pipeline_data`` dict.

    Supports dotted path access, comparison operators, boolean combinators,
    built-in functions, and JMESPath queries via the ``jq()`` function.
    """

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

    def _parse_or(self, tokens: list[_Token], pos: int, data: dict) -> tuple[Any, int]:
        left, pos = self._parse_and(tokens, pos, data)
        while pos < len(tokens) and tokens[pos].kind == "OR":
            pos += 1
            right, pos = self._parse_and(tokens, pos, data)
            left = left or right
        return left, pos

    def _parse_and(self, tokens: list[_Token], pos: int, data: dict) -> tuple[Any, int]:
        left, pos = self._parse_not(tokens, pos, data)
        while pos < len(tokens) and tokens[pos].kind == "AND":
            pos += 1
            right, pos = self._parse_not(tokens, pos, data)
            left = left and right
        return left, pos

    def _parse_not(self, tokens: list[_Token], pos: int, data: dict) -> tuple[Any, int]:
        if pos < len(tokens) and tokens[pos].kind == "NOT":
            pos += 1
            value, pos = self._parse_not(tokens, pos, data)
            return not value, pos
        return self._parse_comparison(tokens, pos, data)

    def _parse_comparison(self, tokens: list[_Token], pos: int, data: dict) -> tuple[Any, int]:
        left, pos = self._parse_atom(tokens, pos, data)
        if pos < len(tokens) and tokens[pos].kind == "CMP":
            op = tokens[pos].value
            pos += 1
            right, pos = self._parse_atom(tokens, pos, data)
            return _compare(left, right, op), pos
        return left, pos

    def _parse_atom(self, tokens: list[_Token], pos: int, data: dict) -> tuple[Any, int]:
        if pos >= len(tokens):
            return None, pos

        tok = tokens[pos]

        if tok.kind == "LPAREN":
            pos += 1
            value, pos = self._parse_or(tokens, pos, data)
            if pos < len(tokens) and tokens[pos].kind == "RPAREN":
                pos += 1
            return value, pos

        if tok.kind == "FUNC":
            return self._parse_function(tokens, pos, data)

        if tok.kind == "NUMBER":
            val = float(tok.value) if "." in tok.value else int(tok.value)
            return val, pos + 1

        if tok.kind == "STRING":
            return tok.value[1:-1], pos + 1

        if tok.kind == "BOOL":
            return tok.value == "true", pos + 1

        if tok.kind == "NULL":
            return None, pos + 1

        if tok.kind == "IDENT":
            return _resolve_path(data, tok.value), pos + 1

        return None, pos + 1

    def _parse_function(self, tokens: list[_Token], pos: int, data: dict) -> tuple[Any, int]:
        func_name = tokens[pos].value
        pos += 1

        if pos >= len(tokens) or tokens[pos].kind != "LPAREN":
            return False, pos
        pos += 1  # consume '('

        args: list[Any] = []
        while pos < len(tokens) and tokens[pos].kind != "RPAREN":
            if tokens[pos].kind == "COMMA":
                pos += 1
                continue
            val, pos = self._parse_atom(tokens, pos, data)
            args.append(val)

        if pos < len(tokens) and tokens[pos].kind == "RPAREN":
            pos += 1

        return self._call_function(func_name, args, data), pos

    def _call_function(self, name: str, args: list[Any], data: dict) -> Any:
        if name == "jq":
            if not args or not isinstance(args[0], str):
                logger.warning("jq_requires_string_literal")
                return None
            try:
                return jmespath.search(args[0], data, _JMESPATH_OPTIONS)
            except Exception:
                logger.warning("jq_eval_failed", expression=args[0])
                return None

        if name == "exists":
            return args[0] is not None if args else False

        if name == "contains":
            if len(args) < 2:
                return False
            haystack, needle = args[0], args[1]
            if isinstance(haystack, str):
                return str(needle) in haystack
            if isinstance(haystack, (list, dict)):
                return needle in haystack
            return False

        if name == "icontains":
            if len(args) < 2:
                return False
            haystack, needle = args[0], args[1]
            if isinstance(haystack, str):
                return str(needle).lower() in haystack.lower()
            return False

        if name == "lower":
            if not args:
                return None
            val = args[0]
            return val.lower() if isinstance(val, str) else val

        if name == "upper":
            if not args:
                return None
            val = args[0]
            return val.upper() if isinstance(val, str) else val

        logger.warning("unknown_function", name=name)
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(data: dict, path: str) -> Any:
    """Resolve a dotted path like ``steps.sa.outputs.count`` against *data*.

    List values support ``.count`` / ``.length`` / ``.len`` as length accessors.
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
