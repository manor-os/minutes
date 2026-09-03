import pytest
from api.services import llm_config


@pytest.fixture
def manor_client_env(monkeypatch):
    monkeypatch.setenv("MANOR_OAUTH_CLIENT_ID", "minutes-cloud")
    monkeypatch.setenv("MANOR_OAUTH_CLIENT_SECRET", "minutes-secret")
    monkeypatch.setenv("MANOR_API_BASE_URL", "https://manor.test")


def test_resolve_manor_points_at_manor_gateway_not_shared_key(monkeypatch, manor_client_env):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-shared")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    client, model = llm_config.resolve_llm(
        route="manor",
        manor_ctx={"entity_id": "01JZENTITY", "user_id": "usr_1", "business_type": "meeting_note"},
    )

    assert str(client.base_url).rstrip("/") == "https://manor.test/api/v1/llm"
    assert client.api_key != "sk-or-shared"  # the shared provider key never leaves the server
    headers = client.default_headers
    assert headers["X-Manor-Client-Id"] == "minutes-cloud"
    assert headers["X-Manor-Client-Secret"] == "minutes-secret"
    assert headers["X-Manor-Entity-Id"] == "01JZENTITY"
    assert headers["X-Manor-User-Id"] == "usr_1"
    assert headers["X-Manor-Business-Type"] == "meeting_note"
    assert model  # non-empty default


def test_resolve_manor_omits_optional_attribution_headers(manor_client_env):
    client, _ = llm_config.resolve_llm(route="manor", manor_ctx={"entity_id": "01JZENTITY"})
    headers = client.default_headers
    assert "X-Manor-User-Id" not in headers
    assert "X-Manor-Business-Type" not in headers


def test_resolve_manor_requires_entity(manor_client_env):
    with pytest.raises(ValueError):
        llm_config.resolve_llm(route="manor", manor_ctx={"entity_id": ""})
    with pytest.raises(ValueError):
        llm_config.resolve_llm(route="manor", manor_ctx=None)


def test_resolve_manor_requires_client_credentials(monkeypatch):
    monkeypatch.delenv("MANOR_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("MANOR_OAUTH_CLIENT_SECRET", raising=False)
    with pytest.raises(llm_config.ManorGatewayNotConfigured):
        llm_config.resolve_llm(route="manor", manor_ctx={"entity_id": "01JZENTITY"})


def test_manor_api_base_url_derived_from_oauth_token_url(monkeypatch):
    monkeypatch.delenv("MANOR_API_BASE_URL", raising=False)
    monkeypatch.setenv("MANOR_OAUTH_TOKEN_URL", "https://app.manorai.xyz/api/v1/oauth/token")
    assert llm_config.get_manor_api_base_url() == "https://app.manorai.xyz"
    assert llm_config.get_manor_gateway_url() == "https://app.manorai.xyz/api/v1/llm"


def test_manor_api_base_url_explicit_override(monkeypatch):
    monkeypatch.setenv("MANOR_API_BASE_URL", "http://manor-api:8000/")
    assert llm_config.get_manor_gateway_url() == "http://manor-api:8000/api/v1/llm"


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
