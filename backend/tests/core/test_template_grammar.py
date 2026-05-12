"""Tests for the Lark-based expression grammar and interpreter."""

import pytest

from backend.core.template import evaluate_condition, evaluate_expression, render_template
from backend.core.template_ast import TemplateSyntaxError, parse_expression


class TestParseExpression:
    def test_simple_path(self):
        ast = parse_expression("steps.foo.outputs.bar")
        assert ast is not None

    def test_path_with_index(self):
        ast = parse_expression("steps.foo.outputs.detections.0.label")
        assert ast is not None

    def test_string_literal(self):
        ast = parse_expression('"hello world"')
        assert ast is not None

    def test_number_literal(self):
        ast = parse_expression("42")
        assert ast is not None

    def test_boolean_literal(self):
        ast = parse_expression("true")
        assert ast is not None

    def test_null_literal(self):
        ast = parse_expression("null")
        assert ast is not None

    def test_comparison(self):
        ast = parse_expression('steps.foo.outputs.count > 3')
        assert ast is not None

    def test_boolean_and(self):
        ast = parse_expression('x > 3 and y == "hello"')
        assert ast is not None

    def test_boolean_or(self):
        ast = parse_expression('x == 1 or y == 2')
        assert ast is not None

    def test_not(self):
        ast = parse_expression("not x")
        assert ast is not None

    def test_pipe_jmespath(self):
        ast = parse_expression("steps.foo.outputs.detections | length(@)")
        assert ast is not None

    def test_function_call(self):
        ast = parse_expression('contains(steps.foo.outputs.label, "person")')
        assert ast is not None

    def test_nested_function(self):
        ast = parse_expression('contains(lower(steps.foo.outputs.label), "person")')
        assert ast is not None

    def test_parenthesized(self):
        ast = parse_expression("(x > 3) and (y < 5)")
        assert ast is not None

    def test_invalid_expression_raises(self):
        with pytest.raises(TemplateSyntaxError):
            parse_expression("!!! invalid !!!")


class TestEvaluateExpression:
    def test_path_resolution(self):
        data = {"steps": {"scene_1": {"outputs": {"count": 5}}}}
        assert evaluate_expression("steps.scene_1.outputs.count", data) == 5

    def test_string_literal(self):
        assert evaluate_expression('"hello"', {}) == "hello"

    def test_number_literal(self):
        assert evaluate_expression("42", {}) == 42

    def test_boolean_true(self):
        assert evaluate_expression("true", {}) is True

    def test_boolean_false(self):
        assert evaluate_expression("false", {}) is False

    def test_null(self):
        assert evaluate_expression("null", {}) is None

    def test_comparison_gt(self):
        data = {"steps": {"s1": {"outputs": {"count": 5}}}}
        assert evaluate_expression("steps.s1.outputs.count > 3", data) is True
        assert evaluate_expression("steps.s1.outputs.count > 10", data) is False

    def test_comparison_eq(self):
        data = {"steps": {"s1": {"outputs": {"label": "person"}}}}
        assert evaluate_expression('steps.s1.outputs.label == "person"', data) is True
        assert evaluate_expression('steps.s1.outputs.label == "dog"', data) is False

    def test_and(self):
        assert evaluate_expression("true and true", {}) is True
        assert evaluate_expression("true and false", {}) is False

    def test_or(self):
        assert evaluate_expression("true or false", {}) is True
        assert evaluate_expression("false or false", {}) is False

    def test_not(self):
        assert evaluate_expression("not false", {}) is True
        assert evaluate_expression("not true", {}) is False


class TestEvaluateCondition:
    def test_returns_bool(self):
        assert evaluate_condition("true", {}) is True

    def test_non_bool_raises(self):
        from backend.core.template_interpreter import TemplateTypeError
        with pytest.raises(TemplateTypeError):
            evaluate_condition("42", {})


class TestFunctions:
    def test_contains_string(self):
        assert evaluate_expression('contains("hello world", "world")', {}) is True
        assert evaluate_expression('contains("hello world", "foo")', {}) is False

    def test_contains_list(self):
        assert evaluate_expression("contains(detections, 3)", {"detections": [1, 2, 3]}) is True

    def test_icontains(self):
        assert evaluate_expression('icontains("Hello", "hello")', {}) is True
        assert evaluate_expression('icontains("Hello", "foo")', {}) is False

    def test_length(self):
        assert evaluate_expression("length(items)", {"items": [1, 2, 3]}) == 3

    def test_lower(self):
        assert evaluate_expression('lower("HELLO")', {}) == "hello"

    def test_upper(self):
        assert evaluate_expression('upper("hello")', {}) == "HELLO"

    def test_exists(self):
        assert evaluate_expression("exists(x)", {"x": "value"}) is True
        assert evaluate_expression("exists(y)", {"x": "value"}) is False


class TestRenderTemplate:
    def test_simple_path(self):
        result = render_template("Count: {{ steps.s1.outputs.count }}", {"steps": {"s1": {"outputs": {"count": 5}}}})
        assert result == "Count: 5"

    def test_unresolved_left_asis(self):
        result = render_template("{{ nonexistent.path }}", {})
        assert result == "{{ nonexistent.path }}"

    def test_mixed_static_and_dynamic(self):
        result = render_template(
            "The {{ steps.s1.outputs.label }} is in the kitchen",
            {"steps": {"s1": {"outputs": {"label": "person"}}}},
        )
        assert result == "The person is in the kitchen"
