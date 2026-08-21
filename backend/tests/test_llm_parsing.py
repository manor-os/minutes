"""Tests for robust parsing of LLM JSON-array output."""
from api.services.llm_parsing import parse_json_array


def test_fenced_json_truncated_by_max_tokens():
    # Regression: raw fences/brackets/quoted lines were shown as key points
    # when the model's fenced JSON array was cut off before the closing "]"
    text = '''```json
[
  "The meeting was disrupted by a technical issue.",
  "No substantial discussions were captured.",
  "A follow-up meeting may be necessary.",'''
    result = parse_json_array(text)
    assert result == [
        "The meeting was disrupted by a technical issue.",
        "No substantial discussions were captured.",
        "A follow-up meeting may be necessary.",
    ]


def test_fenced_json_well_formed():
    assert parse_json_array('```json\n["a point one", "b point two"]\n```') == [
        "a point one", "b point two",
    ]


def test_plain_json_array():
    assert parse_json_array('["x1234", "y5678"]') == ["x1234", "y5678"]


def test_bullet_list_fallback():
    assert parse_json_array('- First key point here\n- Second key point here') == [
        'First key point here', 'Second key point here',
    ]


def test_numbered_list_fallback():
    assert parse_json_array('1. Alpha decision made\n2) Beta deferred to Q3') == [
        'Alpha decision made', 'Beta deferred to Q3',
    ]


def test_array_embedded_in_prose():
    text = 'Here are the key points:\n["point about budget", "point about hiring"]\nDone!'
    assert parse_json_array(text) == ["point about budget", "point about hiring"]


def test_objects_mode():
    text = '```json\n[{"task": "do x", "assignee": "A"}]\n```'
    assert parse_json_array(text, expect_objects=True) == [{"task": "do x", "assignee": "A"}]


def test_objects_mode_does_not_salvage_strings():
    assert parse_json_array('[{"task": "incomplete', expect_objects=True) == []


def test_empty_and_scaffolding_only():
    assert parse_json_array('') == []
    assert parse_json_array('```json\n[\n```') == []
