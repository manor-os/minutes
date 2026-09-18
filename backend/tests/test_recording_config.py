"""Recording credential policy; all auth, database and provider calls are mocked."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.routers import auth, realtime
from api.services.llm_config import resolve_processing_llm_config
from api.services.stt_config import resolve_stt_config


@pytest.fixture
def server_config(monkeypatch):
    monkeypatch.setenv("STT_MODE", "cloud")
    monkeypatch.setenv("LLM_MODE", "cloud")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-server-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://audio.example.test/v1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://text.example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "synthetic-server-model")


@pytest.fixture
def profile_client(monkeypatch, server_config):
    monkeypatch.setattr(auth, "verify_local_token", lambda token: {
        "email": "owner@example.test", "name": "Owner", "auth_source": "manor",
    })
    monkeypatch.setattr(auth, "get_user_by_email", lambda email: {
        "email": email, "name": "Owner", "stt_api_key": "synthetic-old-user-key",
        "stt_base_url": "https://old.example.test", "llm_api_key": "synthetic-old-llm-key",
        "llm_model": "synthetic-user-model",
    })
    app = FastAPI()
    app.include_router(auth.router)
    with TestClient(app, headers={"Authorization": "Bearer synthetic-token"}) as client:
        yield client


@pytest.mark.parametrize("auth_source", ["manor", "google"])
def test_manor_profile_reports_server_readiness_without_provider_secrets(profile_client, monkeypatch, auth_source):
    monkeypatch.setattr(auth, "verify_local_token", lambda token: {
        "email": "owner@example.test", "name": "Owner", "auth_source": auth_source,
    })
    response = profile_client.get("/api/auth/me")
    info = response.json()
    assert info["stt_configured"] is info["llm_configured"] is True
    assert info["stt_managed_by"] == info["llm_managed_by"] == "manor"
    assert info["has_stt_key"] is info["has_llm_key"] is False
    assert info["stt_base_url"] == info["llm_base_url"] == info["llm_model"] == ""
    assert "synthetic-" not in response.text


def test_manor_profile_does_not_require_a_local_user_row(profile_client, monkeypatch):
    monkeypatch.setattr(auth, "get_user_by_email", lambda email: None)
    response = profile_client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["stt_managed_by"] == "manor"


def test_missing_server_keys_cannot_be_masked_by_old_manor_user_keys(profile_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    info = profile_client.get("/api/auth/me").json()
    assert info["stt_configured"] is info["llm_configured"] is False


def test_separate_server_llm_key_cannot_mask_missing_stt(profile_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-server-llm")
    info = profile_client.get("/api/auth/me").json()
    assert info["stt_configured"] is False
    assert info["llm_configured"] is True


def test_server_local_modes_need_no_key(profile_client, monkeypatch):
    monkeypatch.setenv("STT_MODE", "local")
    monkeypatch.setenv("LLM_MODE", "local")
    monkeypatch.delenv("OPENAI_API_KEY")
    info = profile_client.get("/api/auth/me").json()
    assert info["stt_configured"] is info["llm_configured"] is True


@pytest.mark.parametrize("field", ["stt_api_key", "stt_base_url", "llm_api_key", "llm_model", "llm_base_url"])
@pytest.mark.parametrize("value", [None, "synthetic-override"])
def test_manor_cannot_override_any_provider_field(profile_client, monkeypatch, field, value):
    save = MagicMock()
    monkeypatch.setattr(auth, "update_user_llm_config", save)
    assert profile_client.put("/api/auth/llm-config", json={field: value}).status_code == 403
    save.assert_not_called()


def test_local_account_keeps_own_configuration_and_save_even_on_cloud(profile_client, monkeypatch):
    from api.config import edition
    monkeypatch.setattr(edition, "IS_CLOUD", True)
    monkeypatch.setattr(auth, "verify_local_token", lambda token: {
        "email": "owner@example.test", "name": "Owner", "auth_source": "local",
    })
    save = MagicMock(return_value=True)
    monkeypatch.setattr(auth, "update_user_llm_config", save)
    info = profile_client.get("/api/auth/me").json()
    assert info["stt_managed_by"] == info["llm_managed_by"] == "local"
    assert info["stt_configured"] is info["llm_configured"] is True
    assert info["has_stt_key"] is info["has_llm_key"] is True
    response = profile_client.put("/api/auth/llm-config", json={"stt_api_key": "synthetic-own-key"})
    assert response.status_code == 200
    assert save.call_args.kwargs["stt_api_key"] == "synthetic-own-key"


def test_resolved_user_credentials_never_mutate_server_configuration(server_config):
    before = dict(os.environ)
    user = {"stt_api_key": "synthetic-own-key", "stt_base_url": "https://own.example.test", "llm_model": "kimi"}
    own = resolve_stt_config(manor_managed=False, user_config=user)
    own_llm = resolve_processing_llm_config(manor_managed=False, user_config=user)
    assert own["api_key"] == own_llm["api_key"] == "synthetic-own-key"
    assert own["base_url"] == own_llm["base_url"] == "https://own.example.test"
    assert own_llm["model"] == "moonshotai/kimi-k2.5"
    managed = resolve_stt_config(manor_managed=True, user_config=user)
    managed_llm = resolve_processing_llm_config(manor_managed=True, user_config=user)
    assert managed["api_key"] == managed_llm["api_key"] == "synthetic-server-key"
    assert managed["base_url"] == "https://audio.example.test/v1"
    assert managed_llm["base_url"] == "https://text.example.test/v1"
    assert managed_llm["model"] == "synthetic-server-model"
    assert dict(os.environ) == before


@pytest.fixture
def ws_client(monkeypatch, server_config):
    from api.config import edition
    from api.middleware import auth_middleware
    monkeypatch.setattr(edition, "IS_CLOUD", True)
    principal = {"auth_source": "manor", "user_id": "owner", "entity_id": "entity"}
    authenticate = AsyncMock(return_value=principal)
    monkeypatch.setattr(auth_middleware, "get_authenticated_user", authenticate)
    load_keys = MagicMock(return_value={"stt_api_key": "synthetic-wrong-user-key"})
    monkeypatch.setattr(realtime, "_load_user_stt_config", load_keys)
    provider = MagicMock()
    monkeypatch.setattr(realtime, "OpenAI", provider)
    app = FastAPI()
    app.include_router(realtime.router)
    with TestClient(app) as client:
        yield client, authenticate, load_keys, provider


def test_manor_websocket_uses_server_key_and_ignores_client_credentials(ws_client):
    client, authenticate, load_keys, provider = ws_client
    with client.websocket_connect("/ws/transcribe?token=synthetic-session") as ws:
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"type": "config", "stt_api_key": "synthetic-injected-key", "stt_base_url": "https://wrong.example.test"})
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["message"] == "Session ended"
    authenticate.assert_awaited_once_with(authorization="Bearer synthetic-session", x_api_key=None)
    load_keys.assert_not_called()
    provider.assert_called_once_with(api_key="synthetic-server-key", base_url="https://audio.example.test/v1")


@pytest.mark.parametrize("query", ["", "?token=invalid"])
def test_cloud_websocket_rejects_missing_or_invalid_identity_before_provider(ws_client, query):
    client, authenticate, load_keys, provider = ws_client
    authenticate.side_effect = HTTPException(401, "Invalid session")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/transcribe" + query):
            pass
    provider.assert_not_called()
    load_keys.assert_not_called()


def test_unidentified_community_connection_never_loads_an_arbitrary_user(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(realtime.psycopg2, "connect", connect)
    assert realtime._load_user_stt_config() == {}
    connect.assert_not_called()


@pytest.mark.parametrize("auth_source,owner,expected_key", [
    ("manor", "owner", "synthetic-server-key"),
    ("google", "owner", "synthetic-server-key"),
    ("local", "owner", "synthetic-own-key"),
    ("local", None, "synthetic-server-key"),
])
def test_worker_isolates_meeting_credentials(monkeypatch, server_config, auth_source, owner, expected_key):
    import celery_tasks
    import psycopg2
    from api.services import llm_config, processing_dispatch
    meeting = SimpleNamespace(auth_source=auth_source, created_by_user_id=owner, status="uploading")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = meeting
    monkeypatch.setattr(celery_tasks, "get_db_session", lambda: db)
    db_connect = MagicMock()
    cursor = db_connect.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"stt_api_key": "synthetic-own-key", "llm_api_key": "synthetic-own-key"}
    monkeypatch.setattr(psycopg2, "connect", db_connect)
    transcriber = MagicMock()
    summary = MagicMock()
    llm_client = MagicMock(return_value=object())
    monkeypatch.setattr(celery_tasks, "TranscriptionService", transcriber)
    monkeypatch.setattr(celery_tasks, "SummarizationService", summary)
    monkeypatch.setattr(llm_config, "get_openrouter_client", llm_client)
    monkeypatch.setattr(celery_tasks, "storage", MagicMock(side_effect=ValueError("stop after client setup")))
    monkeypatch.setattr(processing_dispatch, "MeetingStatusStore", MagicMock())
    before = dict(os.environ)
    result = celery_tasks.process_meeting_task.run("meeting", "audio.webm")
    assert result["error"] == "stop after client setup"
    assert transcriber.call_args.kwargs["stt_config"]["api_key"] == expected_key
    assert llm_client.call_args.kwargs["api_key"] == expected_key
    assert summary.call_args.kwargs["model"] == "synthetic-server-model"
    if auth_source == "local" and owner:
        assert cursor.execute.call_args.args[1] == (owner, owner)
    else:
        db_connect.assert_not_called()
    assert dict(os.environ) == before


def test_recording_preserves_proxy_model_default_with_openai_fallback(monkeypatch):
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "LLM_BASE_URL", "LLM_MODEL", "OPENROUTER_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-synthetic-openai-key")
    config = resolve_processing_llm_config(manor_managed=True)
    assert config["base_url"] == "https://openrouter.ai/api/v1"
    assert config["model"] == "moonshotai/kimi-k2.5"
