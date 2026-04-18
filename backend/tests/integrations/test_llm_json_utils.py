"""Tests for backend.integrations.llm.json_utils."""

from backend.integrations.llm.json_utils import clean_llm_json, parse_llm_json


class TestCleanLLMJson:
    def test_plain_json_pass_through(self):
        assert clean_llm_json('{"key": "value"}') == '{"key": "value"}'

    def test_json_fence_stripped(self):
        input_text = '```json\n{"key": "value"}\n```'
        assert clean_llm_json(input_text) == '{"key": "value"}'

    def test_raw_fence_stripped(self):
        input_text = '```\n{"key": "value"}\n```'
        assert clean_llm_json(input_text) == '{"key": "value"}'

    def test_fence_with_trailing_newlines(self):
        input_text = '```json\n\n{"key": "value"}\n\n```  \n'
        assert clean_llm_json(input_text) == '{"key": "value"}'

    def test_whitespace_around_json(self):
        input_text = '  {"key": "value"}  '
        assert clean_llm_json(input_text) == '{"key": "value"}'

    def test_empty_string(self):
        assert clean_llm_json("") == ""

    def test_nested_fences_not_stripped(self):
        """Fences inside JSON string values should not be stripped."""
        input_text = '{"code": "```json\\ninner\\n```"}'
        assert clean_llm_json(input_text) == input_text

    def test_multiple_fences_only_outer_stripped(self):
        """Only the outermost fence is stripped."""
        input_text = '```json\n{"inner": "```not a fence```"}\n```'
        assert clean_llm_json(input_text) == '{"inner": "```not a fence```"}'

    def test_array_json(self):
        input_text = '```json\n[1, 2, 3]\n```'
        assert clean_llm_json(input_text) == '[1, 2, 3]'

    def test_whitespace_only_fence(self):
        input_text = '```json\n\n\n```'
        assert clean_llm_json(input_text) == ''


class TestParseLLMJson:
    def test_valid_json_parsed(self):
        result = parse_llm_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_fence_wrapped_parsed(self):
        result = parse_llm_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_invalid_json_returns_string(self):
        result = parse_llm_json('not json at all')
        assert result == 'not json at all'

    def test_empty_string_returns_empty_string(self):
        result = parse_llm_json("")
        assert result == ""

    def test_array_parsed(self):
        result = parse_llm_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_nested_json_parsed(self):
        input_text = '```json\n{"outer": {"inner": [1, 2]}}\n```'
        result = parse_llm_json(input_text)
        assert result == {"outer": {"inner": [1, 2]}}

    def test_invalid_json_with_fence_returns_original(self):
        """When fences match but content is invalid JSON, original string is returned."""
        result = parse_llm_json('```json\n{broken json\n```')
        assert result == '```json\n{broken json\n```'

    def test_malformed_fence_returns_original(self):
        """When only opening fence exists (no closing), original is returned."""
        result = parse_llm_json('```json\n{broken json')
        assert result == '```json\n{broken json'

    def test_whitespace_around_valid_json_parsed(self):
        result = parse_llm_json('  {"key": "value"}  ')
        assert result == {"key": "value"}
