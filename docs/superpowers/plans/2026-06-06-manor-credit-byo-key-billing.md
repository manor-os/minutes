# Manor Credit & BYO-Key Billing Gateway — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every LLM operation by per-request auth type — Manor SSO users charge their Manor entity credit on the shared key; everyone else runs on their own stored API key — and never cross-bill between the two.

**Architecture:** A new `billing_service` owns the routing decision (`classify`), the Manor credit gate (`ensure_credit`), and Manor usage reporting (`report_usage`). `llm_config.resolve_llm` returns the correct OpenAI-compatible client+model per route (shared key vs. the user's stored key), replacing the current process-wide `os.environ` mutation in the Celery worker (a concurrency bug). A new `auth_source` column on meetings lets the async worker pick the right branch. Endpoints classify the request, gate or key-resolve, and (Manor only) report usage after the LLM call.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, Celery, psycopg2, OpenAI SDK (OpenRouter), PostgreSQL, pytest (added here).

**Spec:** `docs/superpowers/specs/2026-06-06-manor-credit-billing-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/api/services/billing_service.py` (new) | `classify`, `ensure_credit`, `report_usage`, `CreditExhaustedError` |
| `backend/api/services/llm_config.py` (modify) | `resolve_llm(route, user_keys)`, `MissingKeyError` |
| `backend/api/services/local_auth_service.py` (modify) | `get_user_llm_keys_by_id(user_id)` |
| `backend/api/services/summarization_service.py` (modify) | `SummarizationService(client=None, model=None)` injectable |
| `backend/database/models.py` (modify) | `MeetingModel.auth_source` column |
| `backend/database/migrations/010_add_auth_source.sql` (new) | DB migration |
| `backend/database/migrations/init_db.py` (modify) | register migration 010 |
| `backend/api/routers/meetings.py` (modify) | persist `auth_source`; gate upload/retry/chat; chat usage report |
| `backend/celery_tasks.py` (modify) | branch on `auth_source`: key resolution + reporting |
| `backend/tests/` (new) | pytest unit tests + conftest |

---

## Task 0: pytest harness

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/requirements-dev.txt`

- [ ] **Step 1: Create dev requirements**

Create `backend/requirements-dev.txt`:

```
pytest>=8.0.0
respx>=0.21.0
```

- [ ] **Step 2: Install**

Run: `cd backend && pip install -r requirements-dev.txt`
Expected: pytest and respx install successfully.

- [ ] **Step 3: Create test package + conftest**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/conftest.py`:

```python
"""Pytest config: make `api`, `database` importable like the app does."""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Neutralize external connections by default; individual tests override.
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db")
```

- [ ] **Step 4: Verify pytest collects**

Run: `cd backend && python -m pytest tests/ -v`
Expected: `no tests ran` (exit 5) — harness works, no tests yet.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/__init__.py backend/tests/conftest.py backend/requirements-dev.txt
git commit -m "test: add pytest harness for backend unit tests"
```

---

## Task 1: `auth_source` column + migration

**Files:**
- Modify: `backend/database/models.py:48` (after `created_by_user_id`)
- Create: `backend/database/migrations/010_add_auth_source.sql`
- Modify: `backend/database/migrations/init_db.py:82,93`

- [ ] **Step 1: Add column to the model**

In `backend/database/models.py`, immediately after the `created_by_user_id` line (currently line 48), add:

```python
    auth_source = Column(String(16), nullable=False, default="local")  # "manor" (Manor SSO → Manor credit) or "local" (BYO key)
```

- [ ] **Step 2: Expose it in `to_dict()`**

In `backend/database/models.py`, inside `MeetingModel.to_dict()`, after the `"created_by_user_id": ...` line, add:

```python
            "auth_source": self.auth_source or "local",
```

- [ ] **Step 3: Create the migration**

Create `backend/database/migrations/010_add_auth_source.sql`:

```sql
-- Track which auth path created the meeting so the async worker bills correctly.
-- "manor" → Manor SSO user, charge entity credit on shared key.
-- "local" → BYO-key user, run on their own key, no Manor billing.
-- Migration: 010_add_auth_source.sql

ALTER TABLE meetings
    ADD COLUMN IF NOT EXISTS auth_source VARCHAR(16) NOT NULL DEFAULT 'local';
```

- [ ] **Step 4: Register the migration**

In `backend/database/migrations/init_db.py`, add `"010_add_auth_source.sql",` to BOTH migration lists — after the `"009_widen_created_by_user_id.sql",` entry at line 82 (postgres branch) and at line 93 (sqlite branch).

- [ ] **Step 5: Apply and verify**

Run: `cd backend && python database/migrations/init_db.py`
Expected: log line `✓ Migration 010_add_auth_source.sql executed successfully` (or "already applied or safe to skip" on re-run).

- [ ] **Step 6: Commit**

```bash
git add backend/database/models.py backend/database/migrations/010_add_auth_source.sql backend/database/migrations/init_db.py
git commit -m "feat: add auth_source column to meetings"
```

---

## Task 2: `billing_service` — classify, gate, report

**Files:**
- Create: `backend/api/services/billing_service.py`
- Test: `backend/tests/test_billing_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_billing_service.py`:

```python
import pytest
import respx
import httpx

from api.services import billing_service as bs


def test_classify_manor_token():
    assert bs.classify({"token_type": "manor", "entity_id": "42"}) == "manor"


def test_classify_local_when_no_token_type():
    assert bs.classify({"entity_id": "abc"}) == "byo"


def test_classify_local_when_token_type_not_manor():
    assert bs.classify({"token_type": "local"}) == "byo"


def test_ensure_credit_passes_when_unlocked():
    class Auth:
        def check_credit_available(self, entity_id):
            return True
    bs.ensure_credit("42", auth=Auth())  # no raise


def test_ensure_credit_raises_when_locked():
    class Auth:
        def check_credit_available(self, entity_id):
            return False
    with pytest.raises(bs.CreditExhaustedError):
        bs.ensure_credit("42", auth=Auth())


def test_ensure_credit_blocks_when_no_entity():
    with pytest.raises(bs.CreditExhaustedError):
        bs.ensure_credit("", auth=object())


@respx.mock
def test_report_usage_posts_payload(monkeypatch):
    monkeypatch.setenv("JAVA_HOST", "http://java.test")
    route = respx.post("http://java.test/business/tokenLog/record").mock(
        return_value=httpx.Response(200, json={})
    )
    bs.report_usage(
        entity_id="42", user_id="u1", client_name="acme",
        input_tokens=100, output_tokens=50, business_type="meeting_note",
    )
    assert route.called
    sent = route.calls.last.request
    import json as _json
    body = _json.loads(sent.content)
    assert body["entityId"] == "42"
    assert body["userId"] == "u1"
    assert body["clientName"] == "acme"
    assert body["inputToken"] == 100
    assert body["outputToken"] == 50
    assert body["totalToken"] == 150
    assert body["businessType"] == "meeting_note"


def test_report_usage_noop_on_zero_tokens():
    # Must not raise and must not need network.
    bs.report_usage(entity_id="42", user_id="u", client_name="c",
                    input_tokens=0, output_tokens=0, business_type="x")


def test_report_usage_swallows_errors(monkeypatch):
    monkeypatch.setenv("JAVA_HOST", "http://127.0.0.1:1")  # nothing listening
    # Must not raise even though POST fails.
    bs.report_usage(entity_id="42", user_id="u", client_name="c",
                    input_tokens=1, output_tokens=1, business_type="x")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_billing_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.services.billing_service'`.

- [ ] **Step 3: Implement `billing_service`**

Create `backend/api/services/billing_service.py`:

```python
"""
Billing gateway: route each LLM operation by auth type and keep Manor-credit
and BYO-key billing strictly separated.

- classify(user)         -> "manor" | "byo"
- ensure_credit(entity)  -> raises CreditExhaustedError if locked / no entity
- report_usage(...)      -> fire-and-forget POST to Manor Java billing endpoint
"""
import os
from typing import Optional

import httpx
from loguru import logger


class CreditExhaustedError(Exception):
    """Manor entity is locked / out of credit, or unbillable (no entity)."""


def classify(user: dict) -> str:
    """Return "manor" for Manor SSO requests, else "byo"."""
    return "manor" if (user or {}).get("token_type") == "manor" else "byo"


def ensure_credit(entity_id, auth=None) -> None:
    """
    Gate a Manor-path operation on available credit.

    Raises CreditExhaustedError when the entity is locked OR when there is no
    entity_id (a Manor request that cannot be attributed must not run on the
    shared key — that would leak cost across account types).

    Fails OPEN only on a transient backend error: check_credit_available
    already returns True when its DB read raises.
    """
    if not entity_id:
        raise CreditExhaustedError("Manor request without entity_id cannot be billed")
    if auth is None:
        from api.services.auth_service import AuthService
        auth = AuthService()
    if not auth.check_credit_available(int(entity_id) if str(entity_id).isdigit() else entity_id):
        raise CreditExhaustedError(f"Entity {entity_id} is out of credit")


def report_usage(*, entity_id, user_id: Optional[str], client_name: Optional[str],
                 input_tokens: int, output_tokens: int, business_type: str) -> None:
    """Fire-and-forget: POST token usage to Manor Java /business/tokenLog/record."""
    total = (input_tokens or 0) + (output_tokens or 0)
    if total <= 0 or not entity_id:
        return
    java_host = (os.getenv("JAVA_HOST") or os.getenv("MANOR_BACKEND_URL", "http://localhost:8070")).rstrip("/")
    payload = {
        "entityId": str(entity_id),
        "userId": str(user_id) if user_id else None,
        "clientName": client_name or None,
        "inputToken": int(input_tokens or 0),
        "outputToken": int(output_tokens or 0),
        "totalToken": int(total),
        "trackedAgentKey": "meeting_note_taker",
        "businessType": business_type,
    }
    try:
        httpx.post(f"{java_host}/business/tokenLog/record", json=payload, timeout=5.0)
    except Exception as exc:
        logger.warning(f"Failed to report token usage to Manor Java: {exc}")
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && python -m pytest tests/test_billing_service.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/api/services/billing_service.py backend/tests/test_billing_service.py
git commit -m "feat: add billing_service (classify, ensure_credit, report_usage)"
```

---

## Task 3: per-user key resolution (`resolve_llm` + lookup helper)

**Files:**
- Modify: `backend/api/services/local_auth_service.py` (append helper)
- Modify: `backend/api/services/llm_config.py` (append `resolve_llm` + `MissingKeyError`)
- Test: `backend/tests/test_resolve_llm.py`

- [ ] **Step 1: Add the user-keys-by-id helper**

Append to `backend/api/services/local_auth_service.py`:

```python
def get_user_llm_keys_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Return a BYO user's stored LLM keys by users.id (UUID). None if not found."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT llm_api_key, llm_model, llm_base_url, stt_api_key "
                "FROM users WHERE id = %s",
                (str(user_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "llm_api_key": row.get("llm_api_key"),
                "llm_model": row.get("llm_model"),
                "llm_base_url": row.get("llm_base_url"),
                "stt_api_key": row.get("stt_api_key"),
            }
    except Exception as e:
        logger.error(f"get_user_llm_keys_by_id failed: {e}")
        return None
    finally:
        conn.close()
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_resolve_llm.py`:

```python
import pytest
from api.services import llm_config


def test_resolve_manor_uses_shared_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-shared")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    client, model = llm_config.resolve_llm(route="manor", user_keys=None)
    assert client.api_key == "sk-or-shared"
    assert model  # non-empty default


def test_resolve_byo_uses_user_key():
    keys = {"llm_api_key": "sk-user", "llm_base_url": "https://x.test/v1", "llm_model": "my-model"}
    client, model = llm_config.resolve_llm(route="byo", user_keys=keys)
    assert client.api_key == "sk-user"
    assert str(client.base_url).rstrip("/") == "https://x.test/v1"
    assert model == "my-model"


def test_resolve_byo_missing_key_raises():
    with pytest.raises(llm_config.MissingKeyError):
        llm_config.resolve_llm(route="byo", user_keys={"llm_api_key": ""})


def test_resolve_byo_none_keys_raises():
    with pytest.raises(llm_config.MissingKeyError):
        llm_config.resolve_llm(route="byo", user_keys=None)
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_resolve_llm.py -v`
Expected: FAIL — `AttributeError: module 'api.services.llm_config' has no attribute 'resolve_llm'`.

- [ ] **Step 4: Implement `resolve_llm`**

Append to `backend/api/services/llm_config.py`:

```python
class MissingKeyError(Exception):
    """A BYO-key user has no LLM API key configured."""


def resolve_llm(*, route: str, user_keys: Optional[dict]):
    """
    Return (OpenAI-compatible client, model_name) for the given route.

    route == "manor": shared server key + base URL (existing behavior).
    route == "byo":   the user's own llm_api_key / llm_base_url / llm_model.
                      Raises MissingKeyError if no llm_api_key is set.
    """
    if route == "byo":
        keys = user_keys or {}
        api_key = (keys.get("llm_api_key") or "").strip()
        if not api_key:
            raise MissingKeyError("No LLM API key configured. Add one in Settings.")
        base_url = (keys.get("llm_base_url") or _DEFAULT_BASE_URL).rstrip("/")
        model = (keys.get("llm_model") or "").strip() or _DEFAULT_MODEL
        return OpenAI(api_key=api_key, base_url=base_url), model
    # Manor / shared
    return get_openrouter_client(), get_llm_model()
```

Add `from typing import Optional` to the imports at the top of `llm_config.py` if not already present.

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && python -m pytest tests/test_resolve_llm.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/api/services/llm_config.py backend/api/services/local_auth_service.py backend/tests/test_resolve_llm.py
git commit -m "feat: resolve_llm + get_user_llm_keys_by_id for per-user key routing"
```

---

## Task 4: make `SummarizationService` injectable

**Files:**
- Modify: `backend/api/services/summarization_service.py:14-17`
- Test: `backend/tests/test_summarization_injectable.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_summarization_injectable.py`:

```python
from api.services.summarization_service import SummarizationService


def test_accepts_injected_client_and_model():
    sentinel_client = object()
    svc = SummarizationService(client=sentinel_client, model="injected-model")
    assert svc.client is sentinel_client
    assert svc.model == "injected-model"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_summarization_injectable.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'client'`.

- [ ] **Step 3: Make the constructor injectable**

In `backend/api/services/summarization_service.py`, replace the `__init__` (lines 14-17):

```python
    def __init__(self, client=None, model=None):
        self.client = client if client is not None else get_openrouter_client()
        self.model = model if model is not None else get_llm_model()
        logger.info(f"SummarizationService: model={self.model}")
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && python -m pytest tests/test_summarization_injectable.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/services/summarization_service.py backend/tests/test_summarization_injectable.py
git commit -m "refactor: allow injecting client/model into SummarizationService"
```

---

## Task 5: persist `auth_source` at meeting creation

**Files:**
- Modify: `backend/api/routers/meetings.py:1824` (`save_meeting` signature + insert)
- Modify: `backend/api/routers/meetings.py:228` (upload call site)

- [ ] **Step 1: Add `auth_source` to `save_meeting`**

In `backend/api/routers/meetings.py`, change the `save_meeting` signature (line 1824):

```python
async def save_meeting(meeting: Meeting, entity_id, user_id=None, auth_source="local") -> str:
```

And in the `MeetingModel(...)` construction inside it, after the `created_by_user_id=user_id,` line, add:

```python
            auth_source=auth_source,
```

- [ ] **Step 2: Pass `auth_source` from the upload endpoint**

In `backend/api/routers/meetings.py`, just before the `save_meeting(...)` call (currently line 228), add:

```python
        from api.services.billing_service import classify
        meeting_auth_source = classify(user)
```

Then change the `save_meeting` call to pass it:

```python
        meeting_id = await save_meeting(
            meeting,
            entity_id=str(entity_id),
            user_id=str(user_id) if user_id else None,
            auth_source=meeting_auth_source,
        )
```

- [ ] **Step 3: Verify import + app still loads**

Run: `cd backend && python -c "import api.routers.meetings"`
Expected: no error (module imports cleanly).

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/meetings.py
git commit -m "feat: stamp auth_source on meetings at upload time"
```

---

## Task 6: branch the Celery worker on `auth_source`

This replaces the buggy `SELECT ... FROM users LIMIT 1` (wrong user) and the
process-wide `os.environ` mutation (leaks keys across concurrent tasks), and
stops cross-billing BYO users to Manor.

**Files:**
- Modify: `backend/celery_tasks.py:112-166` (key resolution block)
- Modify: `backend/celery_tasks.py:166` (SummarizationService construction)
- Modify: `backend/celery_tasks.py:281-291` (local-vs-cloud summarize call)
- Modify: `backend/celery_tasks.py:343-352` (reporting call)
- Delete: `backend/celery_tasks.py:52-73` (`_report_token_usage`)

- [ ] **Step 1: Replace the key-resolution block**

In `backend/celery_tasks.py`, replace the whole block from the `# In community mode, try to get user's API keys` comment (line ~114) through the `summarization_service = None if llm_mode == "local" else SummarizationService()` line (line ~166) with:

```python
        # Resolve auth path + the right LLM client from the MEETING's creator.
        meeting_row = db.query(MeetingModel).filter(MeetingModel.id == meeting_id).first()
        meeting_auth_source = (getattr(meeting_row, "auth_source", None) or "local") if meeting_row else "local"
        creator_user_id = getattr(meeting_row, "created_by_user_id", None) if meeting_row else None

        stt_mode = os.getenv("STT_MODE", "cloud")
        llm_mode = os.getenv("LLM_MODE", "cloud")
        logger.info(f"Processing modes: STT={stt_mode}, LLM={llm_mode}, auth_source={meeting_auth_source}")

        # BYO users supply their own keys; Manor users use the shared key.
        user_keys = None
        if meeting_auth_source != "manor" and creator_user_id:
            from api.services.local_auth_service import get_user_llm_keys_by_id
            user_keys = get_user_llm_keys_by_id(creator_user_id)

        llm_client = None
        llm_model = None
        if llm_mode != "local":
            from api.services.llm_config import resolve_llm, MissingKeyError
            route = "manor" if meeting_auth_source == "manor" else "byo"
            try:
                llm_client, llm_model = resolve_llm(route=route, user_keys=user_keys)
            except MissingKeyError:
                raise RuntimeError(
                    "No LLM API key available for summarization. "
                    "Please configure your LLM key in Settings."
                )

        # STT key: Manor → shared env; BYO → user's stt_api_key (fallback shared).
        effective_stt_key = (
            (user_keys or {}).get("stt_api_key")
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        if stt_mode != "local" and not effective_stt_key:
            raise RuntimeError(
                "No OpenAI API key available for Whisper transcription. "
                "Please configure your OpenAI key in Settings, or set OPENAI_API_KEY env var."
            )

        transcription_service = (
            None if stt_mode == "local" else TranscriptionService(api_key=effective_stt_key)
        )
        summarization_service = (
            None if llm_mode == "local"
            else SummarizationService(client=llm_client, model=llm_model)
        )
```

> Note: `TranscriptionService(api_key=...)` — if `TranscriptionService.__init__` does not accept `api_key`, fall back to the existing behavior by setting `os.environ["OPENAI_API_KEY"] = effective_stt_key` immediately before this line and constructing `TranscriptionService()`. Verify in Step 2.

- [ ] **Step 2: Verify TranscriptionService signature**

Run: `cd backend && grep -n "def __init__" api/services/transcription_service.py`
If `__init__` accepts an `api_key` argument, keep `TranscriptionService(api_key=effective_stt_key)`. If it does NOT, replace that line with:

```python
        if effective_stt_key:
            os.environ["OPENAI_API_KEY"] = effective_stt_key
        transcription_service = None if stt_mode == "local" else TranscriptionService()
```

- [ ] **Step 3: Remove the duplicate meeting fetch**

Later in the function (originally line ~171) there is a second
`meeting = db.query(MeetingModel).filter(MeetingModel.id == meeting_id).first()`.
Replace that line with a reuse of the row already loaded in Step 1:

```python
        meeting = meeting_row
```

Leave the following `if not meeting:` / `if meeting.status == COMPLETED` checks unchanged.

- [ ] **Step 4: Branch reporting on `auth_source`**

In `backend/celery_tasks.py`, replace the existing `_report_token_usage(...)` call (lines ~343-352) with:

```python
            # Report usage to Manor ONLY for Manor-SSO meetings (BYO users pay
            # their own provider — never cross-bill them to Manor).
            if meeting_auth_source == "manor":
                from api.services.billing_service import report_usage
                summarization_tokens = notes.get("token_cost", {})
                report_usage(
                    entity_id=meeting.entity_id,
                    user_id=creator_user_id,
                    client_name=None,
                    input_tokens=(
                        summarization_tokens.get("summary", {}).get("prompt_tokens", 0)
                        + summarization_tokens.get("key_points", {}).get("prompt_tokens", 0)
                        + summarization_tokens.get("action_items", {}).get("prompt_tokens", 0)
                    ),
                    output_tokens=(
                        summarization_tokens.get("summary", {}).get("completion_tokens", 0)
                        + summarization_tokens.get("key_points", {}).get("completion_tokens", 0)
                        + summarization_tokens.get("action_items", {}).get("completion_tokens", 0)
                    ),
                    business_type="meeting_note",
                )
```

- [ ] **Step 5: Delete the old `_report_token_usage` helper**

In `backend/celery_tasks.py`, delete the entire `_report_token_usage` function (lines 52-73, from `def _report_token_usage` through its `logger.warning(...)` body). Confirm no remaining references:

Run: `cd backend && grep -n "_report_token_usage" celery_tasks.py`
Expected: no output.

- [ ] **Step 6: Verify module imports**

Run: `cd backend && python -c "import celery_tasks"`
Expected: no error.

- [ ] **Step 7: Commit**

```bash
git add backend/celery_tasks.py
git commit -m "fix: per-creator key resolution + Manor-only billing in worker

Replace arbitrary 'users LIMIT 1' lookup and process-wide os.environ key
mutation (leaked across concurrent tasks) with resolve_llm() scoped to the
meeting creator, and only report usage to Manor for auth_source=='manor'."
```

---

## Task 7: gate the upload and retry endpoints

**Files:**
- Modify: `backend/api/routers/meetings.py` (upload ~228, retry ~1017)

- [ ] **Step 1: Gate the upload endpoint**

In `backend/api/routers/meetings.py`, right after `meeting_auth_source = classify(user)` (added in Task 5, line ~229) and before `save_meeting(...)`, add:

```python
        if meeting_auth_source == "manor":
            from api.services.billing_service import ensure_credit, CreditExhaustedError
            try:
                ensure_credit(entity_id)
            except CreditExhaustedError:
                raise HTTPException(status_code=402, detail="额度不足,请充值后再试。")
```

- [ ] **Step 2: Gate the retry endpoint**

In the `retry_processing` endpoint (`backend/api/routers/meetings.py`), after `entity_id = user.get('entity_id')` and its existing `if not entity_id` check (line ~1017), add:

```python
        from api.services.billing_service import classify, ensure_credit, CreditExhaustedError
        if classify(user) == "manor":
            try:
                ensure_credit(entity_id)
            except CreditExhaustedError:
                raise HTTPException(status_code=402, detail="额度不足,请充值后再试。")
```

- [ ] **Step 3: Verify import**

Run: `cd backend && python -c "import api.routers.meetings"`
Expected: no error.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/meetings.py
git commit -m "feat: gate upload/retry on Manor credit (402 when locked)"
```

---

## Task 8: gate + meter the AI chat endpoint

**Files:**
- Modify: `backend/api/routers/meetings.py:741-845` (`chat_with_meeting`)

- [ ] **Step 1: Gate + resolve key before streaming**

In `backend/api/routers/meetings.py`, inside `chat_with_meeting`, after the
`question` validation (line ~756, before "Build context"), add:

```python
    from api.services.billing_service import classify, ensure_credit, CreditExhaustedError, report_usage
    from api.services.llm_config import resolve_llm, MissingKeyError

    route = classify(user)
    creator_user_id = user.get("user_id") or user.get("sub")
    chat_user_keys = None
    if route == "manor":
        try:
            ensure_credit(entity_id)
        except CreditExhaustedError:
            raise HTTPException(status_code=402, detail="额度不足,请充值后再试。")
    else:
        from api.services.local_auth_service import get_user_llm_keys_by_id
        chat_user_keys = get_user_llm_keys_by_id(creator_user_id) if creator_user_id else None
        try:
            resolve_llm(route="byo", user_keys=chat_user_keys)  # validate key presence early
        except MissingKeyError:
            raise HTTPException(status_code=400, detail="请先在「设置」中添加 API key。")
```

- [ ] **Step 2: Use the resolved client + request usage in the cloud stream**

In the same function, in the `else` (cloud) branch of `stream_response()`
(currently constructs `service = SummarizationService()` at line ~813), replace
those lines through the `stream = service.client.chat.completions.create(...)`
call with:

```python
                _client, _model = resolve_llm(route=route, user_keys=chat_user_keys)
                _usage = {"prompt_tokens": 0, "completion_tokens": 0}
                stream = _client.chat.completions.create(
                    model=_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                for chunk in stream:
                    if getattr(chunk, "usage", None):
                        _usage["prompt_tokens"] = chunk.usage.prompt_tokens or 0
                        _usage["completion_tokens"] = chunk.usage.completion_tokens or 0
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield f"data: {json.dumps({'token': delta.content})}\n\n"

                if route == "manor":
                    report_usage(
                        entity_id=entity_id,
                        user_id=creator_user_id,
                        client_name=user.get("client_name"),
                        input_tokens=_usage["prompt_tokens"],
                        output_tokens=_usage["completion_tokens"],
                        business_type="meeting_chat",
                    )
```

> The final usage chunk arrives with empty `choices`; the `if chunk.choices` guard already handles that. If `usage` never arrives, both counts stay 0 and `report_usage` no-ops (acceptable: no phantom charge).

- [ ] **Step 3: Verify import**

Run: `cd backend && python -c "import api.routers.meetings"`
Expected: no error.

- [ ] **Step 4: Manual smoke (optional, needs running stack)**

Run the stack, then as a Manor user with a locked entity:
`curl -s -XPOST localhost:8000/api/meetings/<id>/chat -H 'Authorization: Bearer <manor>' -d '{"question":"hi"}'`
Expected: HTTP 402 with `额度不足`.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/meetings.py
git commit -m "feat: gate + meter AI chat (402 on locked, report Manor usage, BYO key)"
```

---

## Task 9: full test run + spec coverage check

- [ ] **Step 1: Run the whole unit suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: all tests PASS (billing_service 9, resolve_llm 4, summarization 1).

- [ ] **Step 2: Import smoke for the touched modules**

Run: `cd backend && python -c "import api.routers.meetings, celery_tasks, api.services.billing_service, api.services.llm_config"`
Expected: no error.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
git commit -m "test: green unit suite for billing gateway" || echo "nothing to commit"
```

---

## Spec Coverage Map

| Spec requirement | Task |
|---|---|
| Route by `token_type` (`classify`) | 2, 5, 7, 8 |
| Manor gate on `entity.locked` (402) | 2, 7, 8 |
| No-entity Manor request blocked | 2 (`ensure_credit`) |
| Fail-open on locked DB error | 2 (relies on `check_credit_available`) |
| Report usage to Manor (summary) | 6 |
| Report usage to Manor (chat) | 8 |
| Manor-only reporting (no cross-bill) | 6, 8 |
| BYO uses user's stored key | 3, 6, 8 |
| BYO missing key → 400 / fail | 3, 6, 8 |
| `auth_source` carries to worker | 1, 5, 6 |
| Per-creator key (fix LIMIT 1 bug) | 6 |
| No process-wide key mutation | 6 |
| LLM-only billing scope | 6, 8 (summary + chat only) |
| `userId` attribution in report | 2, 6, 8 |
