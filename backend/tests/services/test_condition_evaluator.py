"""Tests for ConditionEvaluator.

Coverage:
- Path resolution and dotted access
- Comparison operators
- Boolean combinators (and / or / not)
- built-in functions: exists, contains, icontains, lower, upper
- jq() function with JMESPath filter projections and custom JMESPath functions
- Integration tests against realistic scene-analysis pipeline data
"""

from __future__ import annotations

import pytest

from backend.services.condition_evaluator import (
    ConditionEvaluator,
    _compare,
    _resolve_path,
    _Token,
    _tokenise,
)


@pytest.fixture
def ev() -> ConditionEvaluator:
    return ConditionEvaluator()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def flat_data() -> dict:
    return {
        "person_detections": {"count": 3, "names": ["alice", "bob"]},
        "logic_response": {"is_notification_needed": True, "severity": "high"},
        "vision_response": "kitchen is empty",
        "items": [1, 2, 3],
        "empty_list": [],
        "score": 0.75,
        "count": 0,
        "flag": False,
        "maybe": None,
        "label": "Person",
    }


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
        {"label": "Person", "confidence": 0.958, "class_id": 0},  # duplicate, uppercase
        {"label": "microwave", "confidence": 0.272, "class_id": 68},
    ]
    detections_img2 = [
        {"label": "chair", "confidence": 0.88, "class_id": 56},
    ]
    hazards = [
        {"name": "stove_unattended", "severity": "medium", "description": "Cooking appliance detected."},
        {"name": "medication_access", "severity": "low", "description": "Medication-like container."},
    ]
    description_img1 = (
        "The image shows a woman in a pink sari standing in a kitchen next to a refrigerator."
    )
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
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_simple_key(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate("score >= 0.5", flat_data) is True

    def test_nested_dict(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate("logic_response.is_notification_needed == true", flat_data) is True

    def test_list_count(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate("items.count == 3", flat_data) is True

    def test_list_length(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate("items.length == 3", flat_data) is True

    def test_list_len(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate("items.len == 3", flat_data) is True

    def test_missing_key_is_none(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("missing == null", {}) is True

    def test_traversal_through_none(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("a.b.c == null", {"a": {"b": None}}) is True

    def test_resolve_path_through_scalar_returns_none(self) -> None:
        assert _resolve_path({"x": 5}, "x.y") is None

    def test_deeply_nested(self, ev: ConditionEvaluator) -> None:
        data = {"a": {"b": {"c": {"d": 42}}}}
        assert ev.evaluate("a.b.c.d == 42", data) is True

    def test_steps_namespace(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        assert (
            ev.evaluate("steps.scene_analysis_1.outputs.scene_detector_available == true", scene_data)
            is True
        )


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------


class TestLiterals:
    def test_integer(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("x == 0", {"x": 0}) is True

    def test_float(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("x >= 0.5", {"x": 0.75}) is True

    def test_negative(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("x == -5", {"x": -5}) is True

    def test_bool_true(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("flag == true", {"flag": True}) is True

    def test_bool_false(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("flag == false", {"flag": False}) is True

    def test_null(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("x == null", {"x": None}) is True

    def test_double_quoted_string(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('name == "alice"', {"name": "alice"}) is True

    def test_single_quoted_string(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("name == 'bob'", {"name": "bob"}) is True

    def test_bare_truthy_path(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("flag", {"flag": True}) is True
        assert ev.evaluate("flag", {"flag": False}) is False


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
    def test_numeric(self, ev: ConditionEvaluator, expr: str, expected: bool) -> None:
        assert ev.evaluate(expr, {"x": 10}) is expected

    def test_type_mismatch_returns_false(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("name > 5", {"name": "alice"}) is False

    def test_compare_unknown_op(self) -> None:
        assert _compare(1, 2, "??") is False


# ---------------------------------------------------------------------------
# Boolean operators
# ---------------------------------------------------------------------------


class TestBooleanOperators:
    def test_and_true(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("a == 1 and b == 2", {"a": 1, "b": 2}) is True

    def test_and_false(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("a == 1 and b == 2", {"a": 0, "b": 2}) is False

    def test_or_either(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("a == 1 or b == 2", {"a": 0, "b": 2}) is True

    def test_or_both_false(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("a == 1 or b == 2", {"a": 0, "b": 0}) is False

    def test_not(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("not flag", {"flag": False}) is True
        assert ev.evaluate("not flag", {"flag": True}) is False

    def test_double_not(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("not not flag", {"flag": True}) is True

    def test_and_higher_precedence_than_or(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("a == 1 or b == 1 and c == 1", {"a": 1, "b": 0, "c": 0}) is True

    def test_parens_override_precedence(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("(a == 1 or b == 1) and c == 1", {"a": 1, "b": 0, "c": 0}) is False


# ---------------------------------------------------------------------------
# exists() and contains()
# ---------------------------------------------------------------------------


class TestExistsContains:
    def test_exists_present(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate("exists(vision_response)", flat_data) is True

    def test_exists_missing(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("exists(missing)", {}) is False

    def test_exists_null(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("exists(x)", {"x": None}) is False

    def test_exists_no_args(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("exists()", {}) is False

    def test_contains_string(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate('contains(vision_response, "empty")', flat_data) is True

    def test_contains_string_false(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate('contains(vision_response, "spaceship")', flat_data) is False

    def test_contains_list_member(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('contains(names, "alice")', {"names": ["alice", "bob"]}) is True

    def test_contains_dict_key(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('contains(obj, "k")', {"obj": {"k": 1}}) is True

    def test_contains_insufficient_args(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("contains(vision_response)", {"vision_response": "x"}) is False

    def test_contains_non_container(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("contains(n, 1)", {"n": 42}) is False


# ---------------------------------------------------------------------------
# icontains()
# ---------------------------------------------------------------------------


class TestIContains:
    def test_exact_match(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('icontains(label, "person")', {"label": "person"}) is True

    def test_case_insensitive_upper(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('icontains(label, "person")', {"label": "Person"}) is True

    def test_case_insensitive_search_upper(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('icontains(label, "PERSON")', {"label": "person"}) is True

    def test_substring_match(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('icontains(desc, "kitchen")', {"desc": "A Woman in the Kitchen area"}) is True

    def test_no_match(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('icontains(label, "car")', {"label": "person"}) is False

    def test_non_string_haystack_returns_false(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('icontains(num, "1")', {"num": 123}) is False

    def test_insufficient_args(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("icontains(label)", {"label": "person"}) is False

    def test_nested_path(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert ev.evaluate('icontains(vision_response, "KITCHEN")', flat_data) is True

    def test_combined_with_and(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        assert (
            ev.evaluate(
                'icontains(vision_response, "kitchen") and logic_response.is_notification_needed == true',
                flat_data,
            )
            is True
        )


# ---------------------------------------------------------------------------
# lower() and upper()
# ---------------------------------------------------------------------------


class TestLowerUpper:
    def test_lower_returns_lowercase(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('lower(label) == "person"', {"label": "Person"}) is True

    def test_lower_already_lowercase(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('lower(label) == "person"', {"label": "person"}) is True

    def test_upper_returns_uppercase(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('upper(label) == "PERSON"', {"label": "person"}) is True

    def test_lower_non_string_passthrough(self, ev: ConditionEvaluator) -> None:
        # Non-string values are returned unchanged.
        assert ev.evaluate("lower(x) == 42", {"x": 42}) is True

    def test_upper_non_string_passthrough(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("upper(x) == 42", {"x": 42}) is True

    def test_lower_no_args(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("lower() == null", {}) is True

    def test_lower_with_contains(self, ev: ConditionEvaluator, flat_data: dict) -> None:
        # lower() composing with existing contains().
        assert ev.evaluate('contains(lower(label), "person")', flat_data) is True


# ---------------------------------------------------------------------------
# jq() -- JMESPath evaluation
# ---------------------------------------------------------------------------


class TestJQ:
    """jq() evaluates a JMESPath expression against the full pipeline_data dict."""

    def test_simple_path(self, ev: ConditionEvaluator) -> None:
        data = {"steps": {"sa": {"outputs": {"count": 5}}}}
        assert ev.evaluate('jq("steps.sa.outputs.count") > 0', data) is True

    def test_filter_exact_label(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?label == 'person']"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_filter_exact_label_no_match(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?label == 'cat']"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is False

    def test_filter_lower_contains(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        # Custom lower() + built-in contains() inside filter projection.
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?contains(lower(label), 'person')]"
            ')") > 0'
        )
        # "person" and "Person" both match.
        assert ev.evaluate(expr, scene_data) is True

    def test_filter_icontains_custom_fn(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        # Custom icontains() function inside a JMESPath filter.
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?icontains(label, 'PERSON')]"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_filter_confidence_threshold(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        # Backtick literals for numeric JSON values in JMESPath filter.
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?confidence > `0.9`]"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_filter_compound_predicate(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        # Multiple conditions with && inside filter projection.
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?label == 'person' && confidence > `0.9`]"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_filter_returns_empty_array_is_falsy(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("steps.scene_analysis_1.outputs.scene_detections'
            "[?label == 'helicopter']"
            '")'
        )
        # Empty array -> falsy -> False.
        assert ev.evaluate(expr, scene_data) is False

    def test_filter_returns_nonempty_array_is_truthy(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("steps.scene_analysis_1.outputs.scene_detections'
            "[?label == 'person']"
            '")'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_string_field_via_jq(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("contains(lower(steps.scene_analysis_1.outputs.scene_description)'
            ", 'kitchen')"
            '")'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_string_field_no_match(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("contains(lower(steps.scene_analysis_1.outputs.scene_description)'
            ", 'gymnasium')"
            '")'
        )
        assert ev.evaluate(expr, scene_data) is False

    def test_hazard_severity_filter(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_hazards'
            "[?severity == 'medium']"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_hazard_severity_high_no_match(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_hazards'
            "[?severity == 'high']"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is False

    def test_count_exact(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        # Exactly 2 person detections (one "person" + one "Person").
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?icontains(label, 'person')]"
            ')") == 2'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_invalid_jmespath_returns_false(self, ev: ConditionEvaluator) -> None:
        # Malformed JMESPath: evaluator should log and return False, not raise.
        assert ev.evaluate('jq("[[[[invalid") > 0', {"x": 1}) is False

    def test_non_string_arg_returns_false(self, ev: ConditionEvaluator) -> None:
        # jq() requires a string literal; passing a resolved path value that
        # happens to be an integer should return False without crashing.
        assert ev.evaluate("jq(count) > 0", {"count": 5}) is False

    def test_no_args_returns_false(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("jq() > 0", {}) is False

    def test_combined_jq_and_icontains(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        jq_part = (
            'jq("length(steps.scene_analysis_1.outputs.scene_detections'
            "[?icontains(label, 'person')]"
            ')") > 0'
        )
        icontains_part = 'icontains(steps.scene_analysis_1.outputs.scene_description, "kitchen")'
        expr = f"{jq_part} and {icontains_part}"
        assert ev.evaluate(expr, scene_data) is True

    def test_jq_or_fallback(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        no_match = (
            'jq("length(steps.scene_analysis_1.outputs.scene_hazards'
            "[?severity == 'critical']"
            ')") > 0'
        )
        has_match = (
            'jq("length(steps.scene_analysis_1.outputs.scene_hazards'
            "[?severity == 'medium']"
            ')") > 0'
        )
        assert ev.evaluate(f"{no_match} or {has_match}", scene_data) is True

    def test_per_image_description_access(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = 'jq("contains(lower(steps.scene_analysis_1.outputs.scene_images[0].scene_description), \'kitchen\')")'
        assert ev.evaluate(expr, scene_data) is True

    def test_per_image_second_image_description(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = 'jq("contains(lower(steps.scene_analysis_1.outputs.scene_images[1].scene_description), \'living room\')")'
        assert ev.evaluate(expr, scene_data) is True

    def test_per_image_detections_filter(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        # Filter detections within the second image only.
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_images[1].scene_detections'
            "[?label == 'chair']"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_per_image_no_hazards_on_second(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_images[1].scene_hazards)") == 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_any_image_has_person(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        # Flatten detections across all images via [] projection, then pipe through a filter.
        expr = (
            'jq("length(steps.scene_analysis_1.outputs.scene_images[].scene_detections[]'
            " | [?label == 'person']"
            ')") > 0'
        )
        assert ev.evaluate(expr, scene_data) is True

    def test_image_count(self, ev: ConditionEvaluator, scene_data: dict) -> None:
        expr = 'jq("length(steps.scene_analysis_1.outputs.scene_images)") == 2'
        assert ev.evaluate(expr, scene_data) is True


# ---------------------------------------------------------------------------
# Edge cases and tokeniser
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_expression(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("", {}) is False

    def test_whitespace_only(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("   ", {}) is False

    def test_malformed_expression(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate('name == "unterminated', {"name": "x"}) is False

    def test_unmatched_paren_tolerated(self, ev: ConditionEvaluator) -> None:
        assert ev.evaluate("(x == 1", {"x": 1}) is True

    def test_tokenise_stream(self) -> None:
        tokens = _tokenise("x > 5 and y == true")
        assert [t.kind for t in tokens] == ["IDENT", "CMP", "NUMBER", "AND", "IDENT", "CMP", "BOOL"]

    def test_tokenise_new_functions(self) -> None:
        tokens = _tokenise('jq("expr") > 0')
        assert tokens[0].kind == "FUNC"
        assert tokens[0].value == "jq"

    def test_unknown_function_returns_false(self, ev: ConditionEvaluator) -> None:
        tokens = [
            _Token(kind="FUNC", value="nonexistent", pos=0),
            _Token(kind="LPAREN", value="(", pos=11),
            _Token(kind="RPAREN", value=")", pos=12),
        ]
        result, _ = ev._parse_function(tokens, 0, {})
        assert result is False

    def test_func_without_lparen(self, ev: ConditionEvaluator) -> None:
        tokens = [_Token(kind="FUNC", value="exists", pos=0)]
        result, _ = ev._parse_function(tokens, 0, {})
        assert result is False
