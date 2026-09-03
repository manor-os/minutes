# Manor Credit Billing & BYO-Key Gateway for Minutes — Design

**Date:** 2026-06-06
**Status:** Superseded for the Manor path — Manor accounts now call the Manor
LLM gateway (`/api/v1/llm/chat/completions`) directly, which gates and bills
credits itself; the `entity.locked` MySQL gate and the Java
`/business/tokenLog/record` reporting described below were removed. See
`docs/docs/configuration/manor-oauth.md` ("LLM Billing Through Manor"). The
BYO-key path is unchanged.
**Scope:** meeting-note-taker (Minutes) backend

## Problem

A single Minutes deployment serves **two kinds of users at once**, and each must
be charged differently:

- **Manor SSO users** → their LLM usage is charged against their Manor credit
  (the entity's credit pool), using the server's shared LLM key.
- **Everyone else** (local email/password login) → bring their own API key; their
  LLM calls run on **their** key and they pay the provider directly. Manor is not
  involved.

The routing signal is **per-request auth type** (`token_type == "manor"`), not a
deployment-wide edition flag. Both auth paths run in the same instance.

## Current State (what exists vs. the real gap)

**Already built:**
- `get_current_user` already verifies **both** a local Minutes JWT and a Manor
  token, returning a payload tagged `token_type == "manor"` for Manor SSO
  (`backend/api/routers/auth.py:460`). Mixed-mode auth routing is feasible today.
- The `users` table already has per-user key columns: `llm_api_key`,
  `llm_base_url`, `llm_model`, `stt_api_key`
  (`backend/api/services/local_auth_service.py:42`).
- Settings plumbing exists: `update_user_llm_config()` to save keys, and an
  endpoint exposing `has_llm_key` / `has_stt_key` / `llm_base_url`
  (`backend/api/routers/auth.py:555`).
- Summarization already reports token usage to Manor's Java billing endpoint
  (`_report_token_usage` in `backend/celery_tasks.py:52`).

**The actual gaps:**
1. **The LLM path never consumes per-user keys.** `get_openrouter_client()` /
   `SummarizationService.__init__` always read the shared env key, so a saved
   `llm_api_key` is never used.
2. **Billing does not branch on auth type.** `_report_token_usage` fires for
   every meeting, which would wrongly charge BYO users to Manor.
3. **The async worker cannot resolve the creator's key** (summarization runs in
   Celery, detached from the request).
4. **The credit gate is unused** (`AuthService.check_credit_available` is never
   called).

## How Manor Billing Works (context)

- Credit lives on the **`entity`** table (`max_credit`, `locked`). `locked='1'`
  = suspended / out of credit.
- Manor's Java backend deducts credit by aggregating the **`client_tokens_log`**
  table (per `entity_id`, with `user_id` as a detail field) against the plan's
  token→credit rates, and triggers Stripe auto-recharge.
- Sub-projects integrate by **fire-and-forget reporting**:
  `POST {JAVA_HOST}/business/tokenLog/record` with
  `{clientName, entityId, userId, inputToken, outputToken, totalToken,
  trackedAgentKey, businessType}`. `manor-multi-agent`'s `behavior_reporter.py`
  is the reference.
- There is **no REST endpoint** for "remaining credit"; the gate reads
  `SELECT locked FROM entity WHERE entity_id = %s` directly (Minutes already has
  this connection via `AuthService`).

## Decisions

1. **Routing signal:** per-request `token_type == "manor"`. Manor SSO →
   Manor-credit path; otherwise → BYO-key path. Both live in one deployment.
2. **Manor path:** shared server LLM key; gate on `entity.locked` (block before
   processing); report token usage after each LLM call so Manor deducts credit.
3. **BYO path:** use the user's stored `llm_api_key` / `llm_base_url` /
   `llm_model` (and `stt_api_key` for transcription). No Manor gate, no Manor
   reporting. If the user has no key, block the LLM operation with a clear
   "add your API key in Settings" message.
4. **Billing scope (Manor path):** **LLM only** — summarization (summary + key
   points + action items) and AI chat. Transcription (STT) is not charged to
   Manor (Manor absorbs STT cost on the shared key).
5. **Attribution (Manor path):** charge the **entity** (Manor's pool is
   per-entity); include `userId` in the report as billing-detail attribution.
6. **Gate granularity:** only operations that produce new LLM consumption are
   gated — create/upload meeting, reprocess, AI chat. Pure reads are never
   blocked.
7. **Enforcement:** Manor gate fails **open** on a *Manor outage* — if the
   `locked` DB check itself errors, allow the operation (don't punish users for a
   transient DB failure). But a Manor request with **no `entity_id`** is
   **blocked** (401/402): it cannot be attributed/billed, so allowing it on the
   shared key would leak cost across account types — which violates the core
   invariant that billing methods stay separated. (Resolved.)

## Architecture

Two cohesive new/updated units, each with one responsibility and an explicit
interface, independently testable.

### A. `backend/api/services/billing_service.py` (new) — the gateway

Owns the routing decision, the Manor credit gate, and Manor usage reporting.
Pure functions over explicit inputs; no hidden global state.

```
classify(user_or_meeting) -> "manor" | "byo"
    # "manor" iff token_type == "manor" (request) or auth_source == "manor"
    # (stored meeting). Otherwise "byo".

ensure_credit(entity_id) -> None        # Manor path only
    # Raises CreditExhaustedError if entity.locked == '1'.
    # Delegates the read to AuthService.check_credit_available (fail-open on
    # DB error). No-op when entity_id falsy (see Open Items for the no-entity
    # edge in a Manor request).

report_usage(*, entity_id, user_id, client_name, input_tokens,
             output_tokens, business_type) -> None    # Manor path only
    # Fire-and-forget POST to {JAVA_HOST}/business/tokenLog/record.
    # No-op when input+output <= 0 or entity_id falsy.
    # Replaces the inline _report_token_usage in celery_tasks.py.
```

`CreditExhaustedError` and `MissingKeyError` are small domain exceptions; the API
layer maps them to **HTTP 402** and **HTTP 400** respectively.

### B. `backend/api/services/llm_config.py` (extend) — per-user key resolution

Today `get_openrouter_client()` reads only env vars. Add a resolver that takes
the caller's key context and returns the right client:

```
resolve_llm(*, route, user_keys) -> (client, model)
    # route == "manor": shared env key (existing behavior).
    # route == "byo":   user_keys.llm_api_key / llm_base_url / llm_model.
    #                   Raise MissingKeyError if llm_api_key is absent.
```

`SummarizationService` and the chat endpoint take a resolved client/model instead
of constructing their own. This is the load-bearing change — it makes saved keys
actually used.

### C. Carry auth context to the async worker

At meeting creation, persist on the meeting:
- `created_by_user_id` (already exists; recently widened to VARCHAR), and
- a new `auth_source` field (`"manor"` | `"local"`).

The Celery summarization task reads `auth_source`:
- `"manor"` → `resolve_llm(route="manor")` + `report_usage(...)`.
- `"local"` → look up the creator's keys from the `users` table by
  `created_by_user_id`; `resolve_llm(route="byo", user_keys=...)`. If no key,
  fail the meeting with a clear "add your API key" status; no Manor reporting.

## Data flow

```
                         REQUEST PATH (create / upload / reprocess / chat)
authenticated user
   │ classify()
   ├── "manor" ──► ensure_credit(entity_id)  ──(locked)──► 402
   │                     │ allowed
   │                     ▼
   │              resolve_llm(route="manor") → shared key
   │                     │  (chat: stream now; meetings: enqueue Celery)
   │                     ▼  after LLM success
   │              report_usage(entity_id, user_id, client_name, in, out, type)
   │                     └─► POST /business/tokenLog/record (fire-and-forget)
   │
   └── "byo" ────► resolve_llm(route="byo", user_keys)
                         ├─ no key ──► 400 "add your API key in Settings"
                         │ key ok
                         ▼
                   LLM on user's key (user pays provider). No gate, no report.

                         ASYNC PATH (Celery summarization)
meeting.auth_source == "manor" → shared key + report_usage
meeting.auth_source == "local" → users[created_by_user_id].llm_api_key
                                  (fail meeting if missing) + no report
```

## User → billing matrix

| User | Signal | LLM key | Who pays | Gate |
|---|---|---|---|---|
| Manor SSO | `token_type=="manor"` | shared server key | Manor entity credit (LLM only) | `entity.locked` → 402 |
| Local / BYO | not manor | user's stored key | user pays provider (LLM + STT) | none (missing key → 400) |

## Error handling

| Condition | Behavior |
|---|---|
| Manor: `entity.locked='1'` | 402, operation rejected, no LLM call |
| Manor: locked DB check raises | Fail open — allow |
| Manor: no `entity_id` on a manor request | Block (401/402) — cannot bill, would leak cost |
| Manor: `report_usage` POST fails | Log warning, never fail user request |
| Manor chat: usage chunk missing | Estimate tokens from text length, still report |
| BYO: no `llm_api_key` | 400 "add your API key in Settings"; meeting marked failed if async |
| BYO: user's key rejected by provider | Surface provider error to user; no Manor involvement |

## Component changes (summary)

1. **`billing_service.py` (new):** `classify`, `ensure_credit`, `report_usage`.
2. **`llm_config.py` (extend):** `resolve_llm(route, user_keys)` + `MissingKeyError`.
3. **`SummarizationService` / chat endpoint:** accept a resolved client+model.
4. **Chat endpoint (`meetings.py:741`):** classify → gate (manor) or key-resolve
   (byo); add `stream_options={"include_usage": True}`; report after stream
   (manor only); 402/400 mapping.
5. **Create/upload/reprocess endpoints:** classify → `ensure_credit` (manor) or
   verify key present (byo) before enqueuing; persist `auth_source`.
6. **Meeting model + migration:** add `auth_source VARCHAR(16)` (default
   `'local'`); migration `010_add_auth_source.sql`.
7. **Celery summarization:** branch on `auth_source` for key + reporting; drop the
   unconditional `_report_token_usage`.

## Testing

- **Unit (billing_service):**
  - `classify`: manor token → "manor"; local → "byo".
  - `ensure_credit`: locked='1' raises; '0' passes; DB error → passes
    (fail-open); empty entity → no-op.
  - `report_usage`: correct payload; no-op on zero tokens / no entity; swallows
    POST errors.
- **Unit (llm_config.resolve_llm):** manor→shared key; byo with key→user client;
  byo without key→MissingKeyError.
- **Integration:**
  - Manor user, entity locked → create returns 402; chat returns 402.
  - Manor user, ok → chat reports usage with `business_type="meeting_chat"`
    (mock Java endpoint); summarization reports.
  - BYO user with key → LLM runs on their key; **no** Manor report.
  - BYO user without key → 400 on chat; async meeting marked failed with the
    "add key" message.

## Open Items (resolve during planning)

1. **`clientName` resolution in the worker:** reuse the existing entity→clientName
   MySQL lookup in `meetings.py` (extract to a shared helper).
2. **`JAVA_HOST` config** must be present in the Celery worker env (already read,
   defaulting to `http://localhost:8070`).
3. **Frontend Settings UX** for adding a key and surfacing the 400 "add key"
   error is assumed to exist (the `has_llm_key` endpoint implies a Settings page);
   confirm during planning whether any frontend change is needed.

## Out of Scope

- Charging transcription (STT) to Manor credit.
- A "remaining credit / balance" display inside Minutes.
- Changes to Manor's Java billing backend (we only call the existing endpoint).
- The cloud `/api/cloud/billing/credits` stub.
