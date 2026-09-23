# Connect Minutes from Manor Integrations

The cloud edition exposes Minutes as a fixed OAuth MCP integration for Manor.
A Manor user opens Integrations, signs in to Minutes with Manor, reviews the
requested access, and explicitly authorizes or cancels the connection.

## Two separate OAuth clients

Do not reuse the two client secrets.

1. **Minutes signs users in through Manor**

   - Minutes variables: `MANOR_OAUTH_CLIENT_ID`,
     `MANOR_OAUTH_CLIENT_SECRET`, `MANOR_OAUTH_AUTHORIZE_URL`,
     `MANOR_OAUTH_TOKEN_URL`, `MANOR_OAUTH_REDIRECT_URI`.
   - Production callback registered in Manor:
     `https://minutes.manorai.xyz/auth/manor-callback`.
   - The browser flow uses state bound to a signed, HttpOnly, SameSite=Lax
     cookie and PKCE S256. HTTPS deployments set the cookie as Secure.

2. **Manor connects to the Minutes MCP server**

   - Minutes variables: `MINUTES_OAUTH_CLIENT_ID`,
     `MINUTES_OAUTH_CLIENT_SECRET`, `MINUTES_OAUTH_REDIRECT_URIS`,
     `MINUTES_OAUTH_CLIENT_NAME`, and `MINUTES_MCP_ALLOWED_ORIGINS`.
   - Manor provider configuration must contain the same client id and secret.
   - Production callback allowlist:
     `["https://app.manorai.xyz/api/v1/integrations/oauth/manor_mcp_minutes/callback"]`.
   - Production MCP origin: `https://app.manorai.xyz`.

Use a unique `JWT_SECRET` and a unique `MINUTES_OAUTH_CLIENT_SECRET`, each at
least 32 characters. Secrets stay in deployment configuration and must never be
committed.

The Manor provider uses these fixed endpoints:

| Purpose | URL |
| --- | --- |
| Authorization UI | `https://minutes.manorai.xyz/oauth/authorize` |
| Token exchange | `https://minutes.manorai.xyz/api/oauth/token` |
| User info | `https://minutes.manorai.xyz/api/oauth/userinfo` |
| Revocation | `https://minutes.manorai.xyz/api/oauth/revoke` |
| MCP | `https://minutes.manorai.xyz/api/mcp/` |

Manor requests `minutes:read minutes:write`. Read permits search, recent
meetings, transcript, summary, action items, details, and statistics. Meeting
chat requires both read and write and goes through the same credit checks and
usage reporting as the Minutes UI.

## Identity and existing functionality

The OAuth grant snapshots the verified Manor user id and entity id already used
by the signed Minutes session. MCP queries therefore use the same tenant key as
the user's existing meetings. The integration does not remap ids, move meeting
ownership, or create a second account.

Recording, upload, retry, live transcription, meeting editing, and the normal
Minutes UI keep their existing authentication and billing paths. OAuth access
tokens are accepted only by the OAuth endpoints and the `/api/mcp` adapter;
they are not general Minutes REST session tokens. Existing service API keys and
Minutes user JWTs continue through the original FastMCP endpoint.

OAuth authorization codes and access/refresh tokens are stored only as SHA-256
digests. Codes expire after five minutes and are single use. Access tokens
expire after one hour. Refresh tokens expire after 30 days, rotate on use, and
reuse of a rotated refresh token revokes that token family. A grant has a
90-day maximum lifetime. Disconnect calls the authenticated revocation endpoint
and revokes the complete selected token family.

The MCP adapter implements the stateless JSON response form of Streamable HTTP
and reports protocol version `2025-03-26`. It validates browser Origin when
present. This deployment is intentionally a preconfigured first-party Manor
integration; it does not advertise OAuth dynamic-client discovery for arbitrary
third-party MCP clients.

## Verification

Run the backend suite with an isolated SQLite database and a strong synthetic
JWT secret:

```bash
DATABASE_URL=sqlite:////tmp/minutes-tests.sqlite \
JWT_SECRET=synthetic-test-secret-at-least-thirty-two-characters \
EDITION=cloud \
pytest -q backend/tests
```

Production verification must cover the browser consent redirect, userinfo,
MCP initialize/list/call, refresh, disconnect/revoke, and tenant isolation with
one known meeting in the connected Manor entity.
