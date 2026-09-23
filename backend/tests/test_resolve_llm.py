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
