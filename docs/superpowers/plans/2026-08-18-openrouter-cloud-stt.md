# OpenRouter Cloud STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cloud BYOK and global OpenRouter STT work without breaking OSS or direct OpenAI transcription, then deploy and verify a retryable meeting.

**Architecture:** Cloud retains the current precedence of owner BYOK settings over environment defaults. OpenRouter receives JSON transcription responses, while direct OpenAI preserves verbose timestamp responses. The realtime socket resolves its authenticated user's configuration instead of an arbitrary configured user.

**Tech Stack:** Python 3.11, FastAPI, Celery, OpenAI Python SDK, pytest, React/Vite, Docker Compose.

---

### Task 1: Add OpenRouter response-format regression tests

**Files:**
- Create: `backend/tests/test_openrouter_transcription.py`
- Test: `backend/api/services/transcription_service.py`, `backend/api/routers/realtime.py`

- [ ] **Step 1: Write a failing batch OpenRouter test**

```python
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
```

- [ ] **Step 2: Write a direct OpenAI preservation test**

```python
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
```

- [ ] **Step 3: Write a failing realtime normalization test**

```python
def test_realtime_transcription_returns_text_from_json_response(tmp_path):
    audio = tmp_path / "chunk.webm"
    audio.write_bytes(b"x" * 1024)
    client = FakeClient(text="Live transcript")

    assert _whisper_transcribe(client, str(audio)) == "Live transcript"
    assert client.calls[0]["response_format"] == "json"
```

- [ ] **Step 4: Run the test file**

Run: `pytest backend/tests/test_openrouter_transcription.py -v`

Expected: FAIL because batch code sends `verbose_json` to OpenRouter and realtime sends `text` then returns the SDK response object.

### Task 2: Implement provider-compatible transcription

**Files:**
- Modify: `backend/api/services/transcription_service.py:27-31,148-155,285-292`
- Modify: `backend/api/routers/realtime.py:192-198`
- Test: `backend/tests/test_openrouter_transcription.py`

- [ ] **Step 1: Add provider-aware batch request options**

```python
def _transcription_options(self) -> dict:
    if "openrouter.ai" in (self.base_url or ""):
        return {"response_format": "json"}
    return {
        "response_format": "verbose_json",
        "timestamp_granularities": ["word", "segment"],
    }
```

Store `self.base_url` in `__init__`, pass the returned dictionary into both normal and chunked batch calls, and use `getattr(transcript, "language", None)` because an OpenRouter JSON response may omit language.

- [ ] **Step 2: Normalize realtime JSON**

```python
result = client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_file,
    response_format="json",
    **({"language": language} if language else {}),
)
return result.text if isinstance(getattr(result, "text", None), str) else ""
```

- [ ] **Step 3: Verify green**

Run: `pytest backend/tests/test_openrouter_transcription.py -v`

Expected: PASS.

### Task 3: Scope realtime BYOK to the authenticated Cloud user

**Files:**
- Modify: `backend/api/routers/realtime.py:22-96`
- Modify: `phone-recorder/src/components/Recorder.jsx:139-147`
- Test: `backend/tests/test_openrouter_transcription.py`

- [ ] **Step 1: Add a failing ownership test**

```python
def test_load_user_stt_config_queries_authenticated_user(monkeypatch):
    cursor = FakeCursor({"stt_api_key": "sk-or-user", "stt_base_url": "https://openrouter.ai/api/v1"})
    monkeypatch.setattr(realtime.psycopg2, "connect", lambda *args, **kwargs: FakeConnection(cursor))

    config = realtime._load_user_stt_config(user_id="user-123", email="user@example.com")

    assert config["stt_api_key"] == "sk-or-user"
    assert cursor.params == ("user-123", "user@example.com")
```

- [ ] **Step 2: Verify the test fails**

Run: `pytest backend/tests/test_openrouter_transcription.py::test_load_user_stt_config_queries_authenticated_user -v`

Expected: FAIL because the current resolver accepts no identity and runs an unscoped `LIMIT 1` query.

- [ ] **Step 3: Implement authenticated resolution**

```python
def _load_user_stt_config(user_id: str | None = None, email: str | None = None) -> dict:
    if user_id or email:
        cur.execute(
            "SELECT stt_api_key, stt_base_url FROM users "
            "WHERE (id::text = %s OR email = %s) AND stt_api_key IS NOT NULL AND stt_api_key != '' LIMIT 1",
            (user_id or "", email or ""),
        )
```

Keep the decoded socket JWT payload and call the resolver with `user_id` and `email`. Add the already-issued frontend JWT to the socket query string. For local/OSS connections without a token, retain the existing fallback behavior.

- [ ] **Step 4: Verify the test file is green**

Run: `pytest backend/tests/test_openrouter_transcription.py -v`

Expected: PASS.

### Task 4: Pass Cloud global defaults into the runtime containers

**Files:**
- Modify: `docker-compose.cloud.yml:4-25`
- Modify: `.env.example:1-16`

- [ ] **Step 1: Add Cloud-only pass-through to backend and celery-worker**

```yaml
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-}
      - OPENROUTER_BASE_URL=${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}
      - LLM_MODEL=${LLM_MODEL:-moonshotai/kimi-k2.5}
      - STT_MODE=${STT_MODE:-cloud}
      - LLM_MODE=${LLM_MODE:-cloud}
```

Leave `docker-compose.community.yml` unchanged so OSS remains independent of the Cloud global settings.

- [ ] **Step 2: Document non-secret defaults**

```dotenv
# Cloud shared defaults. Per-user BYOK overrides these during Cloud processing.
OPENAI_BASE_URL=https://api.openai.com/v1
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=moonshotai/kimi-k2.5
STT_MODE=cloud
LLM_MODE=cloud
```

- [ ] **Step 3: Render production Compose**

Run: `docker compose -f docker-compose.yml -f docker-compose.cloud.yml -f docker-compose.prod.yml config --quiet`

Expected: exit 0.

### Task 5: Publish and verify production

**Files:**
- Modify: `/home/ec2-user/meeting-note-taker/.env` on production only

- [ ] **Step 1: Run the full backend suite and frontend build**

Run: `pytest backend/tests -v` and `npm --prefix phone-recorder run build`

Expected: both exit 0.

- [ ] **Step 2: Commit and push**

```bash
git add backend/api/services/transcription_service.py backend/api/routers/realtime.py phone-recorder/src/components/Recorder.jsx docker-compose.cloud.yml .env.example backend/tests/test_openrouter_transcription.py docs/superpowers/plans/2026-08-18-openrouter-cloud-stt.md
git commit -m "fix: support OpenRouter transcription in cloud"
git push origin dev
```

- [ ] **Step 3: Deploy from production**

```bash
git pull --ff-only origin dev
docker compose -f docker-compose.yml -f docker-compose.cloud.yml -f docker-compose.prod.yml up -d --build --force-recreate backend celery-worker celery-beat phone-recorder
```

- [ ] **Step 4: Verify runtime and retry**

Confirm Cloud Base URLs are present in backend and celery, retry meeting `64f3686c-176b-4c2a-9988-05c892f9f1ea`, then confirm its worker request reaches OpenRouter without a `400` response-format error and the meeting leaves `failed`.
