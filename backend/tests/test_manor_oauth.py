import asyncio

import pytest
import respx
import httpx
import jwt

from api.routers.cloud import manor_oauth
from api.services import local_auth_service


@respx.mock
def test_google_login_exchanges_code_with_manor_and_returns_minutes_token(monkeypatch):
    monkeypatch.setenv(
        "MANOR_GOOGLE_OAUTH_URL",
        "https://app.manorai.xyz/api/v1/auth/oauth/google",
    )
    monkeypatch.setenv(
        "MANOR_GOOGLE_PROFILE_URL",
        "https://app.manorai.xyz/api/v1/auth/me",
    )
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    oauth_route = respx.post(
        "https://app.manorai.xyz/api/v1/auth/oauth/google"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "manor-token",
                "token_type": "bearer",
                "user_id": "usr_123",
                "entity_id": "01JZMANORENTITY0000000000",
                "role": "owner",
            },
        )
    )
    profile_route = respx.get("https://app.manorai.xyz/api/v1/auth/me").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "usr_123",
                "email": "alice@example.com",
                "display_name": "Alice",
                "entity_id": "01JZMANORENTITY0000000000",
                "role": "owner",
            },
        )
    )

    result = asyncio.run(
        manor_oauth.google_login(
            manor_oauth.GoogleLoginRequest(
                code="google-code",
                redirect_uri="https://minutes.manorai.xyz/googleCallback",
                state="state-123",
            )
        )
    )

    assert result["success"] is True
    assert result["entity_id"] == "01JZMANORENTITY0000000000"
    assert result["email"] == "alice@example.com"
    assert result["name"] == "Alice"

    assert oauth_route.called
    assert oauth_route.calls.last.request.headers["content-type"] == "application/json"
    assert oauth_route.calls.last.request.content == (
        b'{"code":"google-code","redirect_uri":"https://minutes.manorai.xyz/googleCallback"}'
    )

    assert profile_route.called
    assert profile_route.calls.last.request.headers["authorization"] == "Bearer manor-token"

    claims = jwt.decode(result["token"], local_auth_service.JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == "usr_123"
    assert claims["email"] == "alice@example.com"
    assert claims["entity_id"] == "01JZMANORENTITY0000000000"
    assert claims["auth_source"] == "google"
    assert claims["google_token"] == "manor-token"


def test_google_login_requires_authorization_code():
    with pytest.raises(Exception) as exc:
        asyncio.run(manor_oauth.google_login(manor_oauth.GoogleLoginRequest()))

    assert getattr(exc.value, "status_code", None) == 400
    assert "authorization code" in exc.value.detail


def test_google_login_rejects_cached_implicit_flow_payload_with_refresh_hint():
    with pytest.raises(Exception) as exc:
        asyncio.run(
            manor_oauth.google_login(
                manor_oauth.GoogleLoginRequest(
                    access_token="old-google-access-token",
                    token_type="Bearer",
                )
            )
        )

    assert getattr(exc.value, "status_code", None) == 409
    assert "out of date" in exc.value.detail
    assert "refresh" in exc.value.detail
