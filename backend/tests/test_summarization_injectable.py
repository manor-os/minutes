from types import SimpleNamespace

from api.services.summarization_service import SummarizationService


def test_accepts_injected_client_and_model():
    sentinel_client = object()
    svc = SummarizationService(client=sentinel_client, model="injected-model")
    assert svc.client is sentinel_client
    assert svc.model == "injected-model"


class FakeCompletions:
    def __init__(self, contents):
        self.contents = iter(contents)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.contents)))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


def _service_with_responses(*contents):
    completions = FakeCompletions(contents)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return SummarizationService(client=client, model="test-model"), completions


def test_nonempty_short_transcript_is_sent_to_the_summary_model():
    service, completions = _service_with_responses("Best-effort summary")

    summary, _ = service.summarize("有内容")

    assert summary == "Best-effort summary"
    assert len(completions.calls) == 1


def test_notes_generated_with_a_single_merged_call():
    service, completions = _service_with_responses(
        '{"summary": "## Overview\\nDiscussed the plan.", '
        '"key_points": ["Key decision"], '
        '"action_items": [{"task": "Follow up", "assignee": "Team", "due_date": "TBD"}]}',
    )

    notes = service.generate_meeting_notes("这是一段有实际内容的会议转写文本。")

    assert notes["summary"].startswith("## Overview")
    assert notes["key_points"] == ["Key decision"]
    assert notes["action_items"] == [
        {"task": "Follow up", "assignee": "Team", "due_date": "TBD"}
    ]
    # One merged structured-output call instead of three separate ones
    assert len(completions.calls) == 1
    assert completions.calls[0]["response_format"] == {"type": "json_object"}


def test_merged_call_accepts_fenced_json_and_legacy_item_keys():
    service, completions = _service_with_responses(
        '```json\n{"summary": "S", "key_points": [{"text": "From object"}], '
        '"action_items": [{"description": "Do x", "deadline": "Friday"}]}\n```',
    )

    notes = service.generate_meeting_notes("有内容的转写")

    assert notes["key_points"] == ["From object"]
    assert notes["action_items"] == [
        {"task": "Do x", "assignee": "TBD", "due_date": "Friday"}
    ]
    assert len(completions.calls) == 1


def test_unusable_merged_output_falls_back_to_per_section_calls():
    service, completions = _service_with_responses(
        "not json at all",                       # merged call -> unusable
        "Best-effort summary",                   # legacy: summarize
        "- Key decision",                        # legacy: key points
        '{"action_items": [{"task": "Follow up", "assignee": "Team", "due_date": "TBD"}]}',
    )

    notes = service.generate_meeting_notes("这是一段有实际内容的会议转写文本。")

    assert notes["summary"] == "Best-effort summary"
    assert notes["key_points"] == ["Key decision"]
    assert notes["action_items"] == [
        {"task": "Follow up", "assignee": "Team", "due_date": "TBD"}
    ]
    assert len(completions.calls) == 4


def test_long_transcript_uses_map_reduce():
    from api.services.summarization_service import CHUNK_CHAR_LIMIT

    part1 = '{"summary": "Part one summary", "key_points": ["P1 point"], "action_items": [{"task": "Follow up", "assignee": "A", "due_date": "TBD"}]}'
    part2 = '{"summary": "Part two summary", "key_points": ["P2 point"], "action_items": [{"task": "follow up", "assignee": "A", "due_date": "TBD"}, {"task": "Ship it", "assignee": "B", "due_date": "Friday"}]}'
    reduced = '{"summary": "Whole-meeting summary", "key_points": ["Merged point"], "action_items": []}'
    service, completions = _service_with_responses(part1, part2, reduced)

    transcript = ("word " * ((CHUNK_CHAR_LIMIT // 5) + 4000)).strip()
    assert len(transcript) > CHUNK_CHAR_LIMIT
    notes = service.generate_meeting_notes(transcript)

    assert notes["summary"] == "Whole-meeting summary"
    assert notes["key_points"] == ["Merged point"]
    # Action items merged in code with case-insensitive dedup by task
    assert notes["action_items"] == [
        {"task": "Follow up", "assignee": "A", "due_date": "TBD"},
        {"task": "Ship it", "assignee": "B", "due_date": "Friday"},
    ]
    assert len(completions.calls) == 3  # 2 map + 1 reduce
    assert notes["token_cost"]["total_tokens"] == 6  # 3 calls x fake usage of 2
