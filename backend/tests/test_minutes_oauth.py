"""OAuth and MCP integration tests without external provider/model calls."""

import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import db as database
from database.models import Base, MeetingModel
from api.mcp_http import AuthenticatedMCPApp
from api.routers.cloud import manor_oauth, minutes_oauth, oauth_service as svc
from api.routers.cloud.oauth_models import AuthorizationCode, Grant, OAuthBase, OAuthToken
from api.services.local_auth_service import generate_external_auth_token, verify_token


REDIRECT = "http://127.0.0.1:18413/api/v1/integrations/oauth/manor_mcp_minutes/callback"
CLIENT_SECRET = "synthetic-minutes-client-secret-" * 2
SSO_SECRET = "synthetic-manor-sso-secret-" * 2
JWT_TEST_SECRET = "synthetic-jwt-secret-at-least-thirty-two-characters"
VERIFIER = "test-verifier-" * 5


@pytest.fixture
def env(monkeypatch, tmp_path):
    import api.services.local_auth_service as local_auth

    monkeypatch.setattr(local_auth, "JWT_SECRET", JWT_TEST_SECRET)
    monkeypatch.setenv("MINUTES_OAUTH_CLIENT_ID", "manor-test")
    monkeypatch.setenv("MINUTES_OAUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("MINUTES_OAUTH_REDIRECT_URIS", json.dumps([REDIRECT]))
    monkeypatch.setenv("MINUTES_OAUTH_CLIENT_NAME", "Manor test")
    monkeypatch.setenv("MANOR_OAUTH_CLIENT_ID", "minutes-sso-test")
    monkeypatch.setenv("MANOR_OAUTH_CLIENT_SECRET", SSO_SECRET)
    monkeypatch.setenv(
        "MANOR_OAUTH_AUTHORIZE_URL", "http://127.0.0.1:18413/oauth/authorize"
    )
    monkeypatch.setenv(
        "MANOR_OAUTH_TOKEN_URL", "http://127.0.0.1:18410/api/v1/oauth/token"
    )
    monkeypatch.setenv(
        "MANOR_OAUTH_REDIRECT_URI", "http://127.0.0.1:18417/auth/manor-callback"
    )
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "minutes-test.db"),
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    OAuthBase.metadata.create_all(engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))

    app = FastAPI()
    app.include_router(minutes_oauth.router)
    app.include_router(manor_oauth.router)
    app.mount("/api/mcp", AuthenticatedMCPApp())
    client = TestClient(app)
    actor = {
        "user_id": "01MANORUSERA",
        "sub": "01MANORUSERA",
        "entity_id": "01MANORENTITYA",
        "email": "alice@example.test",
        "name": "Alice",
        "auth_source": "manor",
    }
    second = {
        "user_id": "01MANORUSERB",
        "sub": "01MANORUSERB",
        "entity_id": "01MANORENTITYB",
        "email": "bob@example.test",
        "name": "Bob",
        "auth_source": "manor",
    }
    with database.get_db() as db:
        for mid, user in (("meeting-a", actor), ("meeting-b", second)):
            db.add(
                MeetingModel(
                    id=mid,
                    title="Synthetic " + mid,
                    audio_file="fixture.webm",
                    platform="phone_recorder",
                    duration=120,
                    status="completed",
                    transcript="Synthetic transcript " + mid,
                    summary="Synthetic summary " + mid,
                    key_points=["Decision"],
                    action_items=[{"text": "Follow up"}],
                    meeting_metadata={"speaker_segments": [{"speaker": "Speaker 1"}]},
                    token_cost={"internal": "must-not-leak"},
                    entity_id=user["entity_id"],
                    created_by_user_id=user["user_id"],
                    auth_source="manor",
                )
            )
    yield SimpleNamespace(client=client, actor=actor, second=second, engine=engine)
    client.close()
    engine.dispose()


def request_values(**extra):
    return {
        "client_id": "manor-test",
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": "minutes:read minutes:write",
        "state": "synthetic-state",
        "code_challenge": svc.challenge(VERIFIER),
        "code_challenge_method": "S256",
        **extra,
    }


def session(actor):
    token = generate_external_auth_token(
        actor, actor["entity_id"], actor.get("auth_source", "manor")
    )
    return {"Authorization": "Bearer " + token}


def grant(env, actor=None, scope="minutes:read minutes:write"):
    response = env.client.post(
        "/api/oauth/authorize",
        json={**request_values(scope=scope), "decision": "approve"},
        headers=session(actor or env.actor),
    )
    assert response.status_code == 200, response.text
    code = parse_qs(urlsplit(response.json()["redirect_to"]).query)["code"][0]
    values = {
        "client_id": "manor-test",
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
        "code": code,
        "code_verifier": VERIFIER,
    }
    response = env.client.post("/api/oauth/token", data=values)
    assert response.status_code == 200, response.text
    return response.json(), values


def mcp(env, access, method, params=None, **headers):
    return env.client.post(
        "/api/mcp/",
        headers={"Authorization": "Bearer " + access, **headers},
        json={"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params is not None else {})},
    )


def call(env, access, name, arguments=None, **headers):
    return mcp(
        env,
        access,
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        **headers,
    )


def test_consent_denial_and_invalid_requests_do_not_create_grants(env):
    denied = env.client.post(
        "/api/oauth/authorize",
        json={**request_values(), "decision": "deny"},
        headers=session(env.actor),
    )
    assert denied.status_code == 200
    assert parse_qs(urlsplit(denied.json()["redirect_to"]).query)["error"] == ["access_denied"]
    for mutation in (
        {"redirect_uri": REDIRECT + "/extra"},
        {"client_id": "unregistered"},
        {"scope": "minutes:admin"},
        {"code_challenge_method": "plain"},
        {"state": ""},
        {"response_type": "token"},
    ):
        response = env.client.get(
            "/api/oauth/authorize",
            params=request_values(**mutation),
            headers=session(env.actor),
        )
        assert response.status_code == 400
    with database.get_db() as db:
        assert db.query(Grant).count() == 0


def test_only_a_manor_backed_minutes_session_can_consent(env):
    local = {**env.actor, "auth_source": "local"}
    response = env.client.get(
        "/api/oauth/authorize", params=request_values(), headers=session(local)
    )
    assert response.status_code == 401


def test_code_pkce_userinfo_and_hashed_persistence(env):
    info = env.client.get(
        "/api/oauth/authorize", params=request_values(), headers=session(env.actor)
    )
    assert info.status_code == 200
    assert info.json()["user"]["manor_entity_id"] == env.actor["entity_id"]

    approved = env.client.post(
        "/api/oauth/authorize",
        json={**request_values(), "decision": "approve"},
        headers=session(env.actor),
    )
    code = parse_qs(urlsplit(approved.json()["redirect_to"]).query)["code"][0]
    token_values = {
        "client_id": "manor-test",
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
        "code": code,
        "code_verifier": VERIFIER,
    }
    wrong = env.client.post(
        "/api/oauth/token", data={**token_values, "code_verifier": "wrong" * 12}
    )
    assert wrong.status_code == 400
    issued = env.client.post("/api/oauth/token", data=token_values)
    assert issued.status_code == 200
    assert env.client.post("/api/oauth/token", data=token_values).status_code == 400
    tokens = issued.json()
    userinfo = env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + tokens["access_token"]},
    )
    assert userinfo.status_code == 200
    assert userinfo.json()["manor_user_id"] == env.actor["user_id"]
    assert userinfo.json()["manor_entity_id"] == env.actor["entity_id"]
    with database.get_db() as db:
        assert db.get(AuthorizationCode, svc.digest(code)) is not None
        assert db.get(AuthorizationCode, code) is None
        assert db.get(OAuthToken, svc.digest(tokens["access_token"])) is not None
        assert db.get(OAuthToken, tokens["access_token"]) is None


def test_refresh_rotation_replay_revokes_family(env):
    tokens, _ = grant(env)
    values = {
        "client_id": "manor-test",
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    }
    rotated = env.client.post("/api/oauth/token", data=values)
    assert rotated.status_code == 200
    assert env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + tokens["access_token"]},
    ).status_code == 401
    assert env.client.post("/api/oauth/token", data=values).status_code == 400
    assert env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + rotated.json()["access_token"]},
    ).status_code == 401


def test_reconnect_retires_every_older_token_family(env):
    first, _ = grant(env)
    second, _ = grant(env)
    assert env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + first["access_token"]},
    ).status_code == 401
    assert env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + second["access_token"]},
    ).status_code == 200


def test_revoke_is_idempotent_and_revokes_access_and_refresh(env):
    tokens, _ = grant(env)
    values = {
        "client_id": "manor-test",
        "client_secret": CLIENT_SECRET,
        "token": tokens["refresh_token"],
    }
    assert env.client.post("/api/oauth/revoke", data=values).status_code == 200
    assert env.client.post("/api/oauth/revoke", data=values).status_code == 200
    assert env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + tokens["access_token"]},
    ).status_code == 401


def test_mcp_protocol_origin_notifications_and_scope(env, monkeypatch):
    read, _ = grant(env, scope="minutes:read")
    initialized = mcp(env, read["access_token"], "initialize")
    assert initialized.status_code == 200
    assert initialized.json()["result"]["protocolVersion"] == "2025-03-26"
    tools = mcp(env, read["access_token"], "tools/list").json()["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "get_action_items" in names
    assert "chat_with_meeting" not in names
    assert mcp(
        env,
        read["access_token"],
        "ping",
        **{"Origin": "https://attacker.example"},
    ).status_code == 403
    assert mcp(
        env,
        read["access_token"],
        "ping",
        **{"MCP-Protocol-Version": "2024-11-05"},
    ).status_code == 400
    notification = env.client.post(
        "/api/mcp/",
        headers={"Authorization": "Bearer " + read["access_token"]},
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert notification.status_code == 202

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("chat handler must not run without both scopes")

    monkeypatch.setattr("api.routers.cloud.minutes_mcp.execute", forbidden)
    result = call(
        env,
        read["access_token"],
        "chat_with_meeting",
        {"meeting_id": "meeting-a", "question": "What happened?"},
    )
    assert result.json()["error"]["code"] == -32603


def test_real_read_tools_preserve_history_and_isolate_entities(env):
    tokens, _ = grant(env)
    access = tokens["access_token"]
    listed = call(env, access, "list_recent_meetings").json()["result"]
    listed_data = json.loads(listed["content"][0]["text"])
    assert [item["id"] for item in listed_data["meetings"]] == ["meeting-a"]
    assert "transcript" not in listed_data["meetings"][0]
    assert "entity_id" not in listed_data["meetings"][0]
    assert "token_cost" not in listed_data["meetings"][0]

    details = call(
        env, access, "get_meeting_details", {"meeting_id": "meeting-a"}
    ).json()["result"]
    detail_data = json.loads(details["content"][0]["text"])
    assert detail_data["speakers"] == ["Speaker 1"]
    assert "transcript" not in detail_data
    assert "audio_file" not in detail_data

    actions = call(
        env, access, "get_action_items", {"meeting_id": "meeting-a"}
    ).json()["result"]
    assert json.loads(actions["content"][0]["text"])["count"] == 1
    denied = call(
        env, access, "get_transcript", {"meeting_id": "meeting-b"}
    ).json()["result"]
    assert denied["isError"] is True


def test_lowercase_bearer_routes_to_oauth_adapter(env):
    tokens, _ = grant(env)
    response = env.client.post(
        "/api/mcp/",
        headers={"Authorization": "bearer " + tokens["access_token"]},
        json={"jsonrpc": "2.0", "id": 7, "method": "ping"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {}


def test_issuer_drift_and_expired_grant_fail_closed(env, monkeypatch):
    tokens, _ = grant(env)
    monkeypatch.setenv(
        "MANOR_OAUTH_TOKEN_URL", "http://127.0.0.1:18411/api/v1/oauth/token"
    )
    assert env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + tokens["access_token"]},
    ).status_code == 401
    monkeypatch.setenv(
        "MANOR_OAUTH_TOKEN_URL", "http://127.0.0.1:18410/api/v1/oauth/token"
    )
    with database.get_db() as db:
        grant_row = db.query(Grant).filter(Grant.revoked_at.is_(None)).one()
        grant_row.created_at = svc.now() - svc.GRANT_SECONDS
    assert env.client.get(
        "/api/oauth/userinfo",
        headers={"Authorization": "Bearer " + tokens["access_token"]},
    ).status_code == 401


def test_safe_login_return_paths():
    assert svc.safe_next("/oauth/authorize?client_id=x") == "/oauth/authorize?client_id=x"
    for unsafe in ("https://evil.example", "//evil.example", "/other", "/oauth/authorize#x"):
        with pytest.raises(Exception):
            svc.safe_next(unsafe)


def test_manor_login_is_browser_bound_pkce_and_preserves_raw_ids(env, monkeypatch):
    class TokenResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "access_token": "upstream-secret-must-not-enter-browser-jwt",
                "user": {
                    "id": env.actor["user_id"],
                    "entity_id": env.actor["entity_id"],
                    "email": env.actor["email"],
                    "name": env.actor["name"],
                },
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, json, headers):
            assert json["code_verifier"]
            return TokenResponse()

    monkeypatch.setattr(manor_oauth.httpx, "AsyncClient", Client)
    start = env.client.get(
        "/api/auth/oauth/manor/start",
        params={"next": "/oauth/authorize?client_id=manor-test"},
    )
    assert start.status_code == 200
    cookie = start.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    authorize = urlsplit(start.json()["authorize_url"])
    params = parse_qs(authorize.query)
    assert params["code_challenge_method"] == ["S256"]

    callback = env.client.post(
        "/api/auth/oauth/manor/callback",
        json={"code": "synthetic-code", "state": start.json()["state"]},
    )
    assert callback.status_code == 200, callback.text
    result = callback.json()
    assert result["entity_id"] == env.actor["entity_id"]
    claims = verify_token(result["token"])
    assert claims["user_id"] == env.actor["user_id"]
    assert claims["entity_id"] == env.actor["entity_id"]
    assert "manor_token" not in claims
    assert result["next"].startswith("/oauth/authorize?")
    assert env.client.post(
        "/api/auth/oauth/manor/callback",
        json={"code": "synthetic-code", "state": start.json()["state"]},
    ).status_code == 400


def test_https_login_callback_sets_secure_cookie(env, monkeypatch):
    monkeypatch.setenv(
        "MANOR_OAUTH_REDIRECT_URI", "https://minutes.example/auth/manor-callback"
    )
    response = env.client.get("/api/auth/oauth/manor/start")
    assert "; Secure" in response.headers["set-cookie"]
