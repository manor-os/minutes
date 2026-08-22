from types import SimpleNamespace

from api.routers import realtime
from api.routers.realtime import _whisper_transcribe
from api.services.transcription_service import TranscriptionService


class FakeTranscriptions:
    def __init__(self, text):
        self.calls = []
        self.text = text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            text=self.text,
            language="en",
            duration=12,
            words=[],
            segments=[],
        )


class FakeClient:
    def __init__(self, text):
        self.audio = SimpleNamespace(transcriptions=FakeTranscriptions(text))

    @property
    def calls(self):
        return self.audio.transcriptions.calls


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.params = params

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def test_openrouter_batch_uses_json_without_timestamps(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    service = TranscriptionService()
    service.client = FakeClient(text="OpenRouter transcript")
    audio = tmp_path / "recording.webm"
    audio.write_bytes(b"x" * 1024)

    result = service.transcribe_with_timestamps(str(audio))

    assert service.client.calls[0]["response_format"] == "json"
    assert "timestamp_granularities" not in service.client.calls[0]
    assert result["text"] == "OpenRouter transcript"


def test_openai_batch_keeps_verbose_timestamp_response(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    service = TranscriptionService()
    service.client = FakeClient(text="OpenAI transcript")
    audio = tmp_path / "recording.webm"
    audio.write_bytes(b"x" * 1024)

    service.transcribe_with_timestamps(str(audio))

    assert service.client.calls[0]["response_format"] == "verbose_json"
    assert service.client.calls[0]["timestamp_granularities"] == ["word", "segment"]


def test_openrouter_chunked_transcription_combines_json_text(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    service = TranscriptionService()
    service.client = FakeClient(text="Chunk transcript")
    service.audio_service.get_audio_duration = lambda _: 1
    service.audio_service.extract_audio_segment = lambda _, output, __, ___: open(
        output, "wb"
    ).write(b"x" * 1024)
    audio = tmp_path / "recording.webm"
    audio.write_bytes(b"x" * 1024)

    result = service._transcribe_in_chunks(str(audio))

    assert result["text"] == "Chunk transcript"
    assert service.client.calls[0]["response_format"] == "json"
    assert "timestamp_granularities" not in service.client.calls[0]


def test_realtime_transcription_returns_text_from_json_response(tmp_path):
    audio = tmp_path / "chunk.webm"
    audio.write_bytes(b"x" * 1024)
    client = FakeClient(text="Live transcript")

    assert _whisper_transcribe(client, str(audio)) == "Live transcript"
    assert client.calls[0]["response_format"] == "json"


def test_load_user_stt_config_queries_authenticated_user(monkeypatch):
    cursor = FakeCursor(
        {
            "stt_api_key": "sk-or-user",
            "stt_base_url": "https://openrouter.ai/api/v1",
        }
    )
    monkeypatch.setattr(
        realtime.psycopg2,
        "connect",
        lambda *args, **kwargs: FakeConnection(cursor),
    )

    config = realtime._load_user_stt_config(
        user_id="user-123", email="user@example.com"
    )

    assert config["stt_api_key"] == "sk-or-user"
    assert cursor.params == ("user-123", "user@example.com")
