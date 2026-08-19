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


def test_generic_corruption_verdict_does_not_skip_note_extraction():
    service, completions = _service_with_responses(
        "The meeting transcript appears to be corrupted or contains non-substantive text.",
        "- Key decision",
        '{"action_items": [{"task": "Follow up", "assignee": "Team", "due_date": "TBD"}]}',
    )

    notes = service.generate_meeting_notes("这是一段有实际内容的会议转写文本。")

    assert notes["key_points"] == ["Key decision"]
    assert notes["action_items"] == [
        {"task": "Follow up", "assignee": "Team", "due_date": "TBD"}
    ]
    assert len(completions.calls) == 3
