"""Tests for :mod:`backend.core.template`."""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.template import render_template, resolve_path


class TestResolvePath:
    def test_simple_dict_key(self) -> None:
        assert resolve_path("name", {"name": "alice"}) == "alice"

    def test_nested_dict_key(self) -> None:
        data = {"user": {"profile": {"age": 30}}}
        assert resolve_path("user.profile.age", data) == 30

    def test_list_index(self) -> None:
        data = {"items": ["a", "b", "c"]}
        assert resolve_path("items.1", data) == "b"

    def test_tuple_index(self) -> None:
        data = {"items": ("x", "y")}
        assert resolve_path("items.0", data) == "x"

    def test_nested_list_then_key(self) -> None:
        data = {"detections": [{"name": "Mom"}, {"name": "Dad"}]}
        assert resolve_path("detections.0.name", data) == "Mom"
        assert resolve_path("detections.1.name", data) == "Dad"

    def test_missing_key_returns_none(self) -> None:
        assert resolve_path("nope", {"name": "alice"}) is None

    def test_missing_nested_key_returns_none(self) -> None:
        assert resolve_path("user.profile.age", {"user": {}}) is None

    def test_out_of_range_index_returns_none(self) -> None:
        assert resolve_path("items.99", {"items": [1, 2]}) is None

    def test_non_numeric_index_on_list_returns_none(self) -> None:
        assert resolve_path("items.name", {"items": [1, 2]}) is None

    def test_attribute_access_on_dataclass(self) -> None:
        @dataclass
        class Point:
            x: int
            y: int

        data = {"pt": Point(x=3, y=4)}
        assert resolve_path("pt.x", data) == 3
        assert resolve_path("pt.y", data) == 4

    def test_missing_attribute_returns_none(self) -> None:
        @dataclass
        class Point:
            x: int

        assert resolve_path("pt.missing", {"pt": Point(x=1)}) is None

    def test_none_in_path_short_circuits(self) -> None:
        assert resolve_path("a.b.c", {"a": None}) is None


class TestRenderTemplate:
    def test_no_placeholders_returns_verbatim(self) -> None:
        assert render_template("hello world", {}) == "hello world"

    def test_simple_substitution(self) -> None:
        assert render_template("Hello {{name}}!", {"name": "Alice"}) == "Hello Alice!"

    def test_whitespace_inside_braces_is_tolerated(self) -> None:
        assert render_template("{{  name  }}", {"name": "Bob"}) == "Bob"

    def test_nested_path(self) -> None:
        data = {"user": {"first": "Ada"}}
        assert render_template("{{user.first}}", data) == "Ada"

    def test_list_index_in_path(self) -> None:
        data = {"people": [{"name": "Zoe"}]}
        out = render_template("Is {{people.0.name}} there?", data)
        assert out == "Is Zoe there?"

    def test_unresolved_placeholder_is_left_intact(self) -> None:
        out = render_template("Hi {{missing}}", {})
        assert out == "Hi {{missing}}"

    def test_dict_value_is_json_encoded(self) -> None:
        out = render_template("{{payload}}", {"payload": {"a": 1}})
        assert out == '{"a": 1}'

    def test_list_value_is_json_encoded(self) -> None:
        out = render_template("{{items}}", {"items": [1, 2, 3]})
        assert out == "[1, 2, 3]"

    def test_non_string_scalar_coerced_via_str(self) -> None:
        assert render_template("{{n}}", {"n": 42}) == "42"

    def test_trigger_vars_exposed_under_trigger_namespace(self) -> None:
        out = render_template("{{trigger.room_name}}", {}, {"room_name": "Kitchen"})
        assert out == "Kitchen"

    def test_trigger_vars_promoted_to_top_level(self) -> None:
        out = render_template("{{room_name}}", {}, {"room_name": "Kitchen"})
        assert out == "Kitchen"

    def test_pipeline_data_takes_priority_over_trigger(self) -> None:
        out = render_template(
            "{{room_name}}",
            {"room_name": "Living Room"},
            {"room_name": "Kitchen"},
        )
        assert out == "Living Room"

    def test_multiple_placeholders(self) -> None:
        out = render_template(
            "{{a}} and {{b}}",
            {"a": "foo", "b": "bar"},
        )
        assert out == "foo and bar"

    def test_fast_path_when_no_braces(self) -> None:
        # If there are no braces, the input is returned identically.
        template = "no placeholders here"
        assert render_template(template, {"a": 1}) is template
