"""Which processing errors are worth retrying.

Regression guard: FileNotFoundError & friends subclass OSError.  Treating them
as transient burned three retries and then stranded the meeting in PROCESSING,
because self.retry() skips the code that marks it FAILED.
"""
import pytest

from celery_tasks import _get_effective_llm_key, is_transient_error


def test_effective_llm_key_falls_back_to_openai_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-global")

    assert _get_effective_llm_key() == "sk-or-global"


@pytest.mark.parametrize("exc", [
    FileNotFoundError("Audio file not found: rec.webm"),
    IsADirectoryError("/app/storage"),
    NotADirectoryError("/app/storage/x"),
    PermissionError("cannot read rec.webm"),
    ValueError("Audio file is empty (0 bytes): rec.webm"),
    ValueError("Transcription returned empty result"),
])
def test_permanent_errors_are_not_retried(exc):
    assert is_transient_error(exc) is False


@pytest.mark.parametrize("exc", [
    ConnectionError("Error 111 connecting to redis:6379. Connection refused."),
    TimeoutError("request timed out"),
    OSError("network unreachable"),
    RuntimeError("Connection reset by peer"),
    RuntimeError("Read timeout on OpenAI API"),
])
def test_transient_errors_are_retried(exc):
    assert is_transient_error(exc) is True


def test_a_missing_file_is_not_mistaken_for_a_network_blip():
    """FileNotFoundError is an OSError; it must still be classed permanent."""
    exc = FileNotFoundError("Audio file not found: rec.webm")
    assert isinstance(exc, OSError)
    assert is_transient_error(exc) is False


def test_unknown_errors_are_not_retried_by_default():
    assert is_transient_error(RuntimeError("summarization produced garbage")) is False
