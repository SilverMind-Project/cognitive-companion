"""Tests for the Lark-based expression grammar and interpreter."""

import pytest

from backend.core.template import evaluate_condition, evaluate_expression, render_template
from backend.core.template_ast import TemplateSyntaxError, parse_expression

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scene_data() -> dict:
    """Realistic pipeline_data produced by scene_analysis step (two images)."""
    detections_img1 = [
        {"label": "person", "confidence": 0.964, "class_id": 0},
        {"label": "refrigerator", "confidence": 0.953, "class_id": 72},
        {"label": "dining table", "confidence": 0.700, "class_id": 60},
        {"label": "bottle", "confidence": 0.687, "class_id": 39},
        {"label": "sink", "confidence": 0.674, "class_id": 71},
        {"label": "toaster", "confidence": 0.443, "class_id": 70},
        {"label": "bowl", "confidence": 0.407, "class_id": 45},
        {"label": "Person", "confidence": 0.958, "class_id": 0},
        {"label": "microwave", "confidence": 0.272, "class_id": 68},
    ]
    detections_img2 = [
        {"label": "chair", "confidence": 0.88, "class_id": 56},
    ]
    hazards = [
        {"name": "stove_unattended", "severity": "medium", "description": "Cooking appliance detected."},
        {"name": "medication_access", "severity": "low", "description": "Medication-like container."},
    ]
    description_img1 = "The image shows a woman in a pink sari standing in a kitchen next to a refrigerator."
    description_img2 = "An empty living room with a chair."
    return {
        "steps": {
            "scene_analysis_1": {
                "step_id": 5,
                "step_type": "scene_analysis",
                "outputs": {
                    "scene_images": [
                        {
                            "image_path": "http://minio/cam1/frame.jpg",
                            "scene_description": description_img1,
                            "scene_detections": detections_img1,
                            "scene_hazards": hazards,
                            "scene_embedding": [],
                        },
                        {
                            "image_path": "http://minio/cam2/frame.jpg",
                            "scene_description": description_img2,
                            "scene_detections": detections_img2,
                            "scene_hazards": [],
                            "scene_embedding": [],
                        },
                    ],
                    "scene_detections": detections_img1 + detections_img2,
                    "scene_description": f"{description_img1}\n---\n{description_img2}",
                    "scene_hazards": hazards,
                    "scene_detector_available": True,
                },
            }
        }
    }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Realistic pipeline data (ported from old test_condition_evaluator.py)
# ---------------------------------------------------------------------------


class TestComplexPathResolution:
    def test_missing_key_returns_none(self):
        assert evaluate_expression("steps.foo.outputs.nonexistent", {"steps": {"foo": {"outputs": {"bar": 1}}}}) is None

    def test_none_result_in_comparison(self):
        data = {"steps": {"s1": {"outputs": {"present": "yes"}}}}
        assert evaluate_condition("steps.s1.outputs.missing == null", data) is True
        assert evaluate_condition("steps.s1.outputs.present == null", data) is False

    def test_traversal_through_none(self):
        data = {"steps": {"s1": {"outputs": None}}}
        assert evaluate_expression("steps.s1.outputs.anything", data) is None


class TestComparisonOperators:
    def test_gt_lt(self):
        data = {"steps": {"s1": {"outputs": {"count": 5}}}}
        assert evaluate_condition("steps.s1.outputs.count > 3", data) is True
        assert evaluate_condition("steps.s1.outputs.count > 10", data) is False
        assert evaluate_condition("steps.s1.outputs.count < 10", data) is True
        assert evaluate_condition("steps.s1.outputs.count < 3", data) is False

    def test_gte_lte(self):
        data = {"steps": {"s1": {"outputs": {"count": 5}}}}
        assert evaluate_condition("steps.s1.outputs.count >= 5", data) is True
        assert evaluate_condition("steps.s1.outputs.count >= 6", data) is False
        assert evaluate_condition("steps.s1.outputs.count <= 5", data) is True
        assert evaluate_condition("steps.s1.outputs.count <= 4", data) is False

    def test_eq_neq(self):
        data = {"steps": {"s1": {"outputs": {"label": "person"}}}}
        assert evaluate_condition('steps.s1.outputs.label == "person"', data) is True
        assert evaluate_condition('steps.s1.outputs.label == "dog"', data) is False
        assert evaluate_condition('steps.s1.outputs.label != "dog"', data) is True
        assert evaluate_condition('steps.s1.outputs.label != "person"', data) is False

    def test_type_mismatch_returns_false(self):
        data = {"steps": {"s1": {"outputs": {"count": 5}}}}
        assert evaluate_condition('steps.s1.outputs.count == "not_a_number"', data) is False


class TestBooleanOperators:
    def test_and_precedence_over_or(self):
        assert evaluate_condition("true and false or true", {}) is True  # (T and F) or T = T

    def test_parens_override_precedence(self):
        assert evaluate_condition("true and (false or true)", {}) is True
        assert evaluate_condition("(true and false) or false", {}) is False

    def test_double_not(self):
        assert evaluate_condition("not not true", {}) is True


class TestRealisticPipelineData:
    def test_person_detected(self, scene_data):
        expr = 'contains(lower(steps.scene_analysis_1.outputs.scene_description), "woman")'
        assert evaluate_condition(expr, scene_data) is True

    def test_kitchen_appliance_found(self, scene_data):
        expr = 'contains(lower(steps.scene_analysis_1.outputs.scene_description), "refrigerator")'
        assert evaluate_condition(expr, scene_data) is True

    def test_no_dog_in_image(self, scene_data):
        expr = 'contains(lower(steps.scene_analysis_1.outputs.scene_description), "dog")'
        assert evaluate_condition(expr, scene_data) is False

    def test_hazards_present(self, scene_data):
        expr = "steps.scene_analysis_1.outputs.scene_hazards | length(@) > 0"
        assert evaluate_condition(expr, scene_data) is True

    def test_detector_available(self, scene_data):
        assert evaluate_condition("steps.scene_analysis_1.outputs.scene_detector_available", scene_data) is True

    def test_combined_expression(self, scene_data):
        expr = (
            'steps.scene_analysis_1.outputs.scene_detector_available '
            'and contains(lower(steps.scene_analysis_1.outputs.scene_description), "kitchen")'
        )
        assert evaluate_condition(expr, scene_data) is True


class TestJMESPathPipes:
    def test_length_of_detections(self, scene_data):
        expr = "steps.scene_analysis_1.outputs.scene_detections | length(@)"
        assert evaluate_expression(expr, scene_data) == 10  # 9 + 1

    def test_empty_list_length(self):
        data = {"items": []}
        assert evaluate_expression("items | length(@)", data) == 0

    def test_pipe_with_path(self):
        data = {"steps": {"s1": {"outputs": {"detections": [{"label": "person"}, {"label": "chair"}]}}}}
        assert evaluate_expression("steps.s1.outputs.detections | length(@)", data) == 2


class TestEdgeCases:
    def test_empty_expression_raises(self):
        with pytest.raises(TemplateSyntaxError):
            evaluate_condition("", {})

    def test_whitespace_only_raises(self):
        with pytest.raises(TemplateSyntaxError):
            evaluate_condition("   ", {})

    def test_unknown_function_raises(self):
        with pytest.raises(TemplateSyntaxError):
            evaluate_expression("nonexistent()", {})
