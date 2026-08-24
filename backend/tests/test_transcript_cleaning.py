"""Tests for Whisper repetition-loop cleanup."""
from api.services.transcript_cleaning import clean_transcription, collapse_repeats


def test_single_token_loop_collapsed():
    # The classic hallucination: one token repeated hundreds of times
    text = ("Dr. " * 300).strip()
    assert collapse_repeats(text) == "Dr. Dr. Dr."


def test_phrase_loop_collapsed():
    text = ("thank you " * 50).strip() + " goodbye"
    assert collapse_repeats(text) == "thank you thank you thank you goodbye"


def test_normal_speech_untouched():
    text = "we agreed to ship on Friday and Bob will follow up with the client"
    assert collapse_repeats(text) == text


def test_legitimate_short_repetition_kept():
    assert collapse_repeats("no no we should wait") == "no no we should wait"


def test_empty_input():
    assert collapse_repeats("") == ""
    text, segments = clean_transcription("", [])
    assert text == "" and segments == []


def test_segments_cleaned_and_duplicate_runs_dropped():
    segments = [{"start": i, "end": i + 1, "text": "Dr. Dr. Dr. Dr. Dr."} for i in range(10)]
    segments.append({"start": 10, "end": 11, "text": "actual content here"})

    text, cleaned = clean_transcription("ignored", segments)

    # Each segment's internal loop collapsed, and the run of identical
    # segments capped at MAX_REPEATS
    assert [s["text"] for s in cleaned] == ["Dr. Dr. Dr."] * 3 + ["actual content here"]
    assert text == "Dr. Dr. Dr. Dr. Dr. Dr. Dr. Dr. Dr. actual content here"


def test_no_segments_falls_back_to_text():
    text, segments = clean_transcription(("hello " * 40).strip(), [])
    assert text == "hello hello hello"
    assert segments == []
