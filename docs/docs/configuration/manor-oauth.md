---
sidebar_position: 1
title: Manor OAuth Setup
---

# Manor OAuth Setup

Manor sign-in is available in the cloud edition only and can run alongside Google sign-in. Community edition keeps the local email/password account flow.

## Configure

Set these variables on the backend:

```bash
EDITION=cloud
MANOR_OAUTH_CLIENT_ID=minutes-cloud
MANOR_OAUTH_CLIENT_SECRET=your-client-secret
MANOR_OAUTH_AUTHORIZE_URL=https://app.manorai.xyz/oauth/authorize
MANOR_OAUTH_TOKEN_URL=https://app.manorai.xyz/api/v1/oauth/token
MANOR_OAUTH_REDIRECT_URI=https://minutes.manorai.xyz/auth/manor-callback
```

`MANOR_OAUTH_REDIRECT_URI` must match the redirect URI registered in Manor. The client secret stays server-side and is never exposed to the frontend.

## Seed Client

On the Manor side, generate or rotate the secret with the same seed script used by `manor-portfolio`, overriding the client id and redirect URIs for Minutes:

```bash
cd /path/to/manor-cloud
MANOR_PMS_OAUTH_CLIENT_ID=minutes-cloud \
MANOR_PMS_OAUTH_REDIRECT_URIS="https://minutes.manorai.xyz/auth/manor-callback,http://localhost:9002/auth/manor-callback,http://localhost:3001/auth/manor-callback" \
python scripts/seed_oauth_client_pms.py
```

The script prints:

```bash
MANOR_OAUTH_CLIENT_ID=minutes-cloud
MANOR_OAUTH_CLIENT_SECRET=<generated-secret>
```

For manual deployments, copy the generated `MANOR_OAUTH_CLIENT_SECRET` into the Minutes deployment `.env`, then restart the backend. For GitHub Actions deployments, use the repository secret flow below.

## GitHub Actions Deploy

For the cloud deployment pipeline, save the generated secret as a GitHub Actions repository secret:

```bash
MANOR_OAUTH_CLIENT_SECRET=<generated-secret>
```

The `deploy-cloud` workflow passes this secret to the production server over SSH and exports it for `docker compose`, so `docker-compose.cloud.yml` can inject it into the backend container:

```bash
MANOR_OAUTH_CLIENT_SECRET=<generated-secret>
```

After rotating the Manor OAuth client secret, update the GitHub Actions secret and rerun the deployment workflow. No manual server-side `.env` edit is needed for the cloud deployment.

## Flow

1. The cloud login page calls `GET /api/auth/oauth/manor/start`.
2. Manor authenticates the user and redirects to `/auth/manor-callback`.
3. The frontend posts the code to `POST /api/auth/oauth/manor/callback`.
4. The backend exchanges the code with Manor, then returns a Minutes JWT for normal API access.

## LLM Billing Through Manor

Minutes never holds a provider key for Manor accounts. Every model call made
for a user who signed in with Manor (or with Google through Manor) goes to the
Manor LLM gateway instead of OpenRouter:

```text
POST {MANOR_API_BASE_URL}/api/v1/llm/chat/completions   (OpenAI wire format)
GET  {MANOR_API_BASE_URL}/api/v1/llm/credit             (credit preflight)
```

The backend authenticates to the gateway with the same `MANOR_OAUTH_CLIENT_ID`
/ `MANOR_OAUTH_CLIENT_SECRET` pair and names the account to bill:

| Header | Value |
|---|---|
| `X-Manor-Client-Id` | `MANOR_OAUTH_CLIENT_ID` |
| `X-Manor-Client-Secret` | `MANOR_OAUTH_CLIENT_SECRET` |
| `X-Manor-Entity-Id` | the user's Manor `entity_id` |
| `X-Manor-User-Id` | the user's Manor user id (attribution) |
| `X-Manor-Business-Type` | `meeting_note` (summaries) or `meeting_chat` (AI chat) |

Manor resolves the model, runs the provider call with its own key and debits
the entity's credits as it goes. When the entity is out of credit the gateway
answers `402`; Minutes refuses new uploads, retries and chat until the account
is topped up and shows the "out of credit" message in the user's language: the
frontend sends the language chosen under Settings → Transcript Language as
`X-Language`, the backend falls back to the browser's `Accept-Language`, and
English is the default (see `backend/api/services/messages.py` for the
translations). Speech-to-text is not routed through Manor and still uses the
server `OPENAI_API_KEY`.

`MANOR_API_BASE_URL` defaults to the origin of `MANOR_OAUTH_TOKEN_URL`, so
existing deployments need no new variable. Locally registered users are
unaffected: they keep using the key saved in Settings and pay their provider
directly.
