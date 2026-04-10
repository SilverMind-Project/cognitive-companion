"""Unit tests for the ``ConditionEvaluator`` recursive-descent parser.

The evaluator is pure and synchronous so every test below works against a
plain dict. We aim to cover every grammar production and every branch of
``_resolve_path`` / ``_compare``.
"""

from __future__ import annotations

import pytest

from backend.services.condition_evaluator import (
    ConditionEvaluator,
    _compare,
    _resolve_path,
    _tokenise,
)


@pytest.fixture
def evaluator() -> ConditionEvaluator:
    return ConditionEvaluator()


@pytest.fixture
def sample_data() -> dict:
    return {
        "person_detections": {"count": 3, "names": ["alice", "bob"]},
        "logic_response": {"is_notification_needed": True, "severity": "high"},
        "vision_response": "kitchen is empty",
        "translation": "hello world",
        "items": [1, 2, 3],
        "empty_list": [],
        "score": 0.75,
        "count": 0,
        "flag": False,
        "maybe": None,
    }


# ---------------------------------------------------------------------------
# Literals and path access
# ---------------------------------------------------------------------------


class TestLiterals:
    def test_integer_literal(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("count == 0", {"count": 0}) is True

    def test_float_literal(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("score >= 0.5", {"score": 0.75}) is True

    def test_negative_number(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("x == -5", {"x": -5}) is True

    def test_true_literal(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("flag == true", {"flag": True}) is True

    def test_false_literal(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("flag == false", {"flag": False}) is True

    def test_null_literal(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("x == null", {"x": None}) is True

    def test_double_quoted_string(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate('name == "alice"', {"name": "alice"}) is True

    def test_single_quoted_string(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("name == 'bob'", {"name": "bob"}) is True


class TestPathResolution:
    def test_nested_dict_access(self, evaluator: ConditionEvaluator, sample_data: dict) -> None:
        assert evaluator.evaluate(
            "logic_response.is_notification_needed == true", sample_data
        ) is True

    def test_list_count_accessor(self, evaluator: ConditionEvaluator, sample_data: dict) -> None:
        assert evaluator.evaluate("items.count == 3", sample_data) is True

    def test_list_length_accessor(self, evaluator: ConditionEvaluator, sample_data: dict) -> None:
        assert evaluator.evaluate("items.length == 3", sample_data) is True

    def test_list_len_accessor(self, evaluator: ConditionEvaluator, sample_data: dict) -> None:
        assert evaluator.evaluate("items.len == 3", sample_data) is True

    def test_missing_key_is_none(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("missing == null", {}) is True

    def test_traversal_through_none(self, evaluator: ConditionEvaluator) -> None:
        # ``a.b.c`` where ``a.b`` is None should return None, not crash.
        assert evaluator.evaluate("a.b.c == null", {"a": {"b": None}}) is True

    def test_traversal_through_scalar(self, evaluator: ConditionEvaluator) -> None:
        # Resolving through a scalar terminal returns None.
        assert _resolve_path({"x": 5}, "x.y") is None

    def test_deeply_nested(self, evaluator: ConditionEvaluator) -> None:
        data = {"a": {"b": {"c": {"d": 42}}}}
        assert evaluator.evaluate("a.b.c.d == 42", data) is True


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------


class TestComparisons:
    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            ("x > 5", True),
            ("x < 5", False),
            ("x >= 10", True),
            ("x <= 10", True),
            ("x == 10", True),
            ("x != 5", True),
        ],
    )
    def test_numeric_comparisons(
        self, evaluator: ConditionEvaluator, expr: str, expected: bool
    ) -> None:
        assert evaluator.evaluate(expr, {"x": 10}) is expected

    def test_type_mismatch_returns_false(self, evaluator: ConditionEvaluator) -> None:
        # Comparing str > int raises TypeError inside _compare; must return False.
        assert evaluator.evaluate('name > 5', {"name": "alice"}) is False

    def test_compare_helper_unknown_operator(self) -> None:
        assert _compare(1, 2, "??") is False

    def test_no_comparison_returns_value(self, evaluator: ConditionEvaluator) -> None:
        # Bare truthy identifier evaluates to the value itself.
        assert evaluator.evaluate("flag", {"flag": True}) is True
        assert evaluator.evaluate("flag", {"flag": False}) is False


# ---------------------------------------------------------------------------
# Boolean operators
# ---------------------------------------------------------------------------


class TestBooleanOperators:
    def test_and_both_true(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("a == 1 and b == 2", {"a": 1, "b": 2}) is True

    def test_and_short_circuits_false(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("a == 1 and b == 2", {"a": 0, "b": 2}) is False

    def test_or_either_true(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("a == 1 or b == 2", {"a": 0, "b": 2}) is True

    def test_or_both_false(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("a == 1 or b == 2", {"a": 0, "b": 0}) is False

    def test_not_inverts(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("not flag", {"flag": False}) is True
        assert evaluator.evaluate("not flag", {"flag": True}) is False

    def test_double_not(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("not not flag", {"flag": True}) is True

    def test_and_has_higher_precedence_than_or(self, evaluator: ConditionEvaluator) -> None:
        # a or (b and c) — if a is true, whole thing is true.
        assert evaluator.evaluate(
            "a == 1 or b == 1 and c == 1", {"a": 1, "b": 0, "c": 0}
        ) is True

    def test_parentheses_override_precedence(
        self, evaluator: ConditionEvaluator
    ) -> None:
        # (a or b) and c — needs both sides.
        assert evaluator.evaluate(
            "(a == 1 or b == 1) and c == 1", {"a": 1, "b": 0, "c": 0}
        ) is False


# ---------------------------------------------------------------------------
# Functions: exists() and contains()
# ---------------------------------------------------------------------------


class TestFunctions:
    def test_exists_true(self, evaluator: ConditionEvaluator, sample_data: dict) -> None:
        assert evaluator.evaluate("exists(translation)", sample_data) is True

    def test_exists_false_for_missing(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("exists(missing)", {}) is False

    def test_exists_false_for_null(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("exists(x)", {"x": None}) is False

    def test_exists_with_no_args(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("exists()", {}) is False

    def test_contains_string(
        self, evaluator: ConditionEvaluator, sample_data: dict
    ) -> None:
        assert evaluator.evaluate(
            'contains(vision_response, "empty")', sample_data
        ) is True

    def test_contains_string_false(
        self, evaluator: ConditionEvaluator, sample_data: dict
    ) -> None:
        assert evaluator.evaluate(
            'contains(vision_response, "spaceship")', sample_data
        ) is False

    def test_contains_list(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate(
            'contains(names, "alice")',
            {"names": ["alice", "bob"]},
        ) is True

    def test_contains_dict_key(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate(
            'contains(obj, "k")', {"obj": {"k": 1}}
        ) is True

    def test_contains_insufficient_args(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate('contains(vision_response)', {"vision_response": "x"}) is False

    def test_contains_on_non_container(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate('contains(n, 1)', {"n": 42}) is False

    def test_unknown_function_returns_false(self, evaluator: ConditionEvaluator) -> None:
        # The tokeniser only recognises ``exists``/``contains``; anything else
        # falls through as an identifier path. This test just guards the
        # FUNC-dispatch fall-through branch in _parse_function by feeding a
        # synthetic FUNC token via tokeniser monkeypatch is overkill — instead
        # we exercise the final ``return False, pos`` by looking at the method
        # directly with a fake function name.
        from backend.services.condition_evaluator import _Token

        tokens = [
            _Token(kind="FUNC", value="wat", pos=0),
            _Token(kind="LPAREN", value="(", pos=3),
            _Token(kind="RPAREN", value=")", pos=4),
        ]
        result, _ = evaluator._parse_function(tokens, 0, {})
        assert result is False

    def test_function_without_lparen_returns_false(
        self, evaluator: ConditionEvaluator
    ) -> None:
        from backend.services.condition_evaluator import _Token

        tokens = [_Token(kind="FUNC", value="exists", pos=0)]
        result, _ = evaluator._parse_function(tokens, 0, {})
        assert result is False


# ---------------------------------------------------------------------------
# Parser edge cases
# ---------------------------------------------------------------------------


class TestParserEdgeCases:
    def test_empty_expression_is_false(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("", {}) is False

    def test_whitespace_only_is_false(self, evaluator: ConditionEvaluator) -> None:
        assert evaluator.evaluate("   ", {}) is False

    def test_malformed_expression_returns_false(
        self, evaluator: ConditionEvaluator
    ) -> None:
        # Unterminated string crashes the tokeniser -> caught, returns False.
        assert evaluator.evaluate('name == "unterminated', {"name": "x"}) is False

    def test_unmatched_paren_is_tolerated(self, evaluator: ConditionEvaluator) -> None:
        # Missing RPAREN is silently accepted — atom returns the inner value.
        assert evaluator.evaluate("(x == 1", {"x": 1}) is True

    def test_tokenise_returns_token_stream(self) -> None:
        tokens = _tokenise("x > 5 and y == true")
        kinds = [t.kind for t in tokens]
        assert kinds == ["IDENT", "CMP", "NUMBER", "AND", "IDENT", "CMP", "BOOL"]
