"""End-to-end test of the Manor OAuth login flow.

Runs entirely in-process:
- A `httpx.MockTransport` plays the role of Manor, dispatching on the
  request path: /oauth/token, /api/me, /api/subscriptions/minutes.
- The minutes auth router is mounted in a FastAPI app driven via
  `fastapi.testclient.TestClient`.
- The DB-touching parts of local_auth_service are monkey-patched to
  an in-memory dict — no PostgreSQL needed.

We drive the flow with TestClient(follow_redirects=False) and assert
each hop: login -> authorize redirect -> code exchange -> userinfo ->
subscription check -> upsert -> final redirect with minutes JWT.
"""
import os
import sys
import urllib.parse as up
from typing import Any, Dict

# Configure env BEFORE any imports so module-level constants pick it up.
os.environ.setdefault("EDITION", "cloud")
os.environ["MANOR_BASE_URL"] = "https://manor.test"
os.environ["MANOR_CLIENT_ID"] = "minutes-test-client"
os.environ["MANOR_CLIENT_SECRET"] = "shh"
os.environ["MANOR_REDIRECT_URI"] = "https://minutes.test/api/auth/manor/callback"
os.environ["MANOR_LOGIN_SUCCESS_REDIRECT"] = "https://minutes-frontend.test/landing"
os.environ["MANOR_LOGIN_FAILURE_REDIRECT"] = "https://minutes-frontend.test/landing"
os.environ["JWT_SECRET"] = "test-jwt-secret-for-the-flow-test"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx
import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --------------------------------------------------------------------------
# Fake Manor — implemented as an httpx.MockTransport handler
# --------------------------------------------------------------------------
TEST_AUTH_CODE = "AUTH_CODE_123"
TEST_ACCESS_TOKEN = "MANOR_ACCESS_TOKEN_XYZ"
TEST_USER = {"id": "manor-user-42", "email": "alice@manor.test", "name": "Alice"}
SUBSCRIPTION_STATE = {"active": True}


def manor_mock(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    auth = request.headers.get("authorization", "")
    if path == "/oauth/token" and request.method == "POST":
        # form-encoded body
        body = dict(up.parse_qsl(request.content.decode()))
        assert body.get("grant_type") == "authorization_code", body
        assert body.get("code") == TEST_AUTH_CODE, body
        assert body.get("client_id") == os.environ["MANOR_CLIENT_ID"], body
        assert body.get("client_secret") == os.environ["MANOR_CLIENT_SECRET"], body
        return httpx.Response(200, json={
            "access_token": TEST_ACCESS_TOKEN, "token_type": "Bearer", "expires_in": 3600,
        })
    if path == "/api/me" and request.method == "GET":
        assert auth == f"Bearer {TEST_ACCESS_TOKEN}", auth
        return httpx.Response(200, json=TEST_USER)
    if path == "/api/subscriptions/minutes" and request.method == "GET":
        assert auth == f"Bearer {TEST_ACCESS_TOKEN}", auth
        product = request.url.params.get("product")
        assert product == "minutes", product
        if SUBSCRIPTION_STATE["active"]:
            return httpx.Response(200, json={"active": True, "status": "active", "plan": "pro"})
        return httpx.Response(200, json={"active": False, "status": "cancelled"})
    return httpx.Response(404, text=f"unhandled {request.method} {path}")


# --------------------------------------------------------------------------
# In-memory DB layer for the auth router
# --------------------------------------------------------------------------
USERS: Dict[str, Dict[str, Any]] = {}


def _fake_init_users_table(*a, **kw): pass
def _fake_seed_default_admin(*a, **kw): return False


def _fake_upsert_oauth_user(email: str, manor_user_id: str, name: str = ""):
    email = email.lower().strip()
    if email in USERS:
        USERS[email].update({"manor_user_id": manor_user_id, "name": USERS[email].get("name") or name})
    else:
        USERS[email] = {"id": f"local-{len(USERS)+1}", "email": email, "name": name, "manor_user_id": manor_user_id}
    return USERS[email]


import api.services.local_auth_service as las
las.init_users_table = _fake_init_users_table
las.seed_default_admin = _fake_seed_default_admin
las.upsert_oauth_user = _fake_upsert_oauth_user

# --------------------------------------------------------------------------
# Patch manor_auth_service's httpx to use the MockTransport
# --------------------------------------------------------------------------
import api.services.manor_auth_service as mas

_mock_transport = httpx.MockTransport(manor_mock)


class _ManorHttpxShim:
    """Stand-in for the `httpx` module visible inside manor_auth_service."""
    HTTPError = httpx.HTTPError
    Timeout = httpx.Timeout

    @staticmethod
    def Client(*a, **kw):
        kw.pop("timeout", None)
        kw.pop("transport", None)
        kw.pop("base_url", None)
        return httpx.Client(transport=_mock_transport, base_url="https://manor.test")


mas.httpx = _ManorHttpxShim

# --------------------------------------------------------------------------
# Build the minutes test app
# --------------------------------------------------------------------------
import importlib.util
_AUTH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api", "routers", "auth.py")
spec = importlib.util.spec_from_file_location("_auth_router", _AUTH_PATH)
auth_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth_mod)
# Rebind names that were imported `from` into the auth module namespace.
auth_mod.upsert_oauth_user = _fake_upsert_oauth_user

minutes_app = FastAPI()
minutes_app.include_router(auth_mod.router)
client = TestClient(minutes_app, follow_redirects=False)

# --------------------------------------------------------------------------
# Drive the flow
# --------------------------------------------------------------------------
results = []


def ok(label, cond, extra=""):
    mark = "OK  " if cond else "FAIL"
    results.append((mark, label, extra))
    print(f"  [{mark}] {label}  {extra}")


print("=== 1. GET /api/auth/manor/login ===")
r = client.get("/api/auth/manor/login")
ok("returns 302", r.status_code == 302, f"status={r.status_code}")
loc = r.headers.get("location", "")
print(f"  -> Location: {loc[:160]}...")
parsed = up.urlparse(loc)
qs = dict(up.parse_qsl(parsed.query))
ok("redirects to MANOR_BASE_URL/oauth/authorize",
   parsed.netloc == "manor.test" and parsed.path == "/oauth/authorize")
ok("carries client_id", qs.get("client_id") == os.environ["MANOR_CLIENT_ID"])
ok("carries redirect_uri", qs.get("redirect_uri") == os.environ["MANOR_REDIRECT_URI"])
ok("carries response_type=code", qs.get("response_type") == "code")
ok("carries non-empty state (JWT)", bool(qs.get("state")) and qs["state"].count(".") == 2)
state_token = qs["state"]
decoded_state = pyjwt.decode(state_token, os.environ["JWT_SECRET"], algorithms=["HS256"])
ok("state is signed JWT with purpose=manor_oauth_state",
   decoded_state.get("purpose") == "manor_oauth_state")

print()
print("=== 2. Simulated Manor login → callback with valid code + state ===")
r = client.get(f"/api/auth/manor/callback?code={TEST_AUTH_CODE}&state={state_token}")
ok("returns 302", r.status_code == 302, f"status={r.status_code}")
loc = r.headers.get("location", "")
print(f"  -> Location: {loc[:200]}")
parsed = up.urlparse(loc)
qs = dict(up.parse_qsl(parsed.query))
ok("lands on MANOR_LOGIN_SUCCESS_REDIRECT",
   f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == os.environ["MANOR_LOGIN_SUCCESS_REDIRECT"])
ok("got minutes JWT in token=", "token" in qs and qs["token"].count(".") == 2)
ok("got entity_id", "entity_id" in qs)
ok("got email", qs.get("email") == TEST_USER["email"])
ok("no error param", "error" not in qs)

minutes_jwt = qs["token"]
payload = pyjwt.decode(minutes_jwt, os.environ["JWT_SECRET"], algorithms=["HS256"])
print(f"  -> minutes JWT payload: email={payload.get('email')} entity_id={payload.get('entity_id')} name={payload.get('name')}")
ok("JWT email matches", payload.get("email") == TEST_USER["email"])
ok("JWT entity_id is int", isinstance(payload.get("entity_id"), int))

ok("user was upserted with manor_user_id",
   USERS[TEST_USER["email"]]["manor_user_id"] == TEST_USER["id"])

print()
print("=== 3. Callback with tampered state → rejected ===")
r = client.get(f"/api/auth/manor/callback?code={TEST_AUTH_CODE}&state=not-a-real-state")
loc = r.headers.get("location", "")
qs = dict(up.parse_qsl(up.urlparse(loc).query))
ok("redirects with error=invalid_state",
   r.status_code == 302 and qs.get("error") == "invalid_state", f"loc={loc}")

print()
print("=== 4. Callback when Manor reports no active subscription ===")
SUBSCRIPTION_STATE["active"] = False
fresh_state = mas.build_state("")
r = client.get(f"/api/auth/manor/callback?code={TEST_AUTH_CODE}&state={fresh_state}")
loc = r.headers.get("location", "")
qs = dict(up.parse_qsl(up.urlparse(loc).query))
ok("redirects with error=no_subscription",
   r.status_code == 302 and qs.get("error") == "no_subscription", f"loc={loc}")
ok("did not issue a JWT", "token" not in qs)

print()
print("=== 5. Callback when Manor returns OAuth error ===")
r = client.get("/api/auth/manor/callback?error=access_denied")
loc = r.headers.get("location", "")
qs = dict(up.parse_qsl(up.urlparse(loc).query))
ok("propagates provider error",
   r.status_code == 302 and qs.get("error") == "access_denied", f"loc={loc}")

print()
print("=== 6. GET /api/auth/manor/enabled ===")
r = client.get("/api/auth/manor/enabled")
ok("returns 200", r.status_code == 200, f"status={r.status_code}")
ok("reports enabled=true (cloud + configured)", r.json().get("enabled") is True, f"body={r.json()}")

print()
print("=== 7. Redirect allowlist ===")
# A Chrome-extension redirect URL must be accepted out-of-the-box.
ext_redirect = "https://abcdef0123456789.chromiumapp.org/"
r = client.get(f"/api/auth/manor/login?redirect={up.quote(ext_redirect, safe='')}")
ok("chromiumapp.org redirect accepted", r.status_code == 302, f"status={r.status_code}, body={r.text[:200]}")
# Same-origin as MANOR_LOGIN_SUCCESS_REDIRECT must be accepted.
r = client.get(f"/api/auth/manor/login?redirect={up.quote(os.environ['MANOR_LOGIN_SUCCESS_REDIRECT'], safe='')}")
ok("configured success-redirect accepted", r.status_code == 302)
# Anything else must be rejected.
r = client.get(f"/api/auth/manor/login?redirect=https://evil.example.com/steal")
ok("attacker-controlled redirect rejected", r.status_code == 400, f"status={r.status_code}")

print()
print("=== 8. Extension flow: errors land on the requested redirect ===")
SUBSCRIPTION_STATE["active"] = False
ext_state = mas.build_state(ext_redirect)
r = client.get(f"/api/auth/manor/callback?code={TEST_AUTH_CODE}&state={ext_state}")
loc = r.headers.get("location", "")
parsed_loc = up.urlparse(loc)
qs = dict(up.parse_qsl(parsed_loc.query))
ok(
    "error redirects to extension URL (chromiumapp.org), not configured failure target",
    parsed_loc.netloc.endswith(".chromiumapp.org") and qs.get("error") == "no_subscription",
    f"loc={loc}",
)

print()
print("=== 9. Extension flow: success lands on the requested redirect ===")
SUBSCRIPTION_STATE["active"] = True
ext_state = mas.build_state(ext_redirect)
r = client.get(f"/api/auth/manor/callback?code={TEST_AUTH_CODE}&state={ext_state}")
loc = r.headers.get("location", "")
parsed_loc = up.urlparse(loc)
qs = dict(up.parse_qsl(parsed_loc.query))
ok(
    "success redirects to extension URL with token",
    parsed_loc.netloc.endswith(".chromiumapp.org") and "token" in qs,
    f"loc={loc[:200]}",
)

print()
fails = [r for r in results if r[0].strip() == "FAIL"]
print(f"=== Summary: {len(results) - len(fails)}/{len(results)} checks passed ===")
sys.exit(1 if fails else 0)
