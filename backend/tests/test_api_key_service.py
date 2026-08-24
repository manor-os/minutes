"""Multi-key support in the API key service."""
import importlib

import pytest


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    from api.services import api_key_service as module
    svc = module.APIKeyService.__new__(module.APIKeyService)
    svc.valid_api_key = ""
    return svc


def test_no_keys_configured_rejects_everything(service):
    assert service.validate_api_key("anything") is False
    assert service.validate_api_key(None) is False


def test_single_key_matches(service):
    service.valid_api_key = "alpha"
    assert service.validate_api_key("alpha") is True
    assert service.validate_api_key("beta") is False


def test_comma_separated_keys_all_valid(service):
    service.valid_api_key = "alpha, beta,gamma"
    assert service.validate_api_key("alpha") is True
    assert service.validate_api_key("beta") is True
    assert service.validate_api_key("gamma") is True
    assert service.validate_api_key("delta") is False


def test_empty_segments_are_not_keys(service):
    service.valid_api_key = ",alpha,,"
    assert service.validate_api_key("") is False
    assert service.validate_api_key("alpha") is True


def test_key_derived_from_manor_oauth_client_secret(service, monkeypatch):
    import hashlib
    import hmac as hmac_mod

    monkeypatch.setenv("MANOR_OAUTH_CLIENT_SECRET", "shared-client-secret")
    derived = hmac_mod.new(
        b"shared-client-secret",
        b"manor-minutes-mcp-service-key-v1",
        hashlib.sha256,
    ).hexdigest()

    assert service.validate_api_key(derived) is True
    # Explicit env keys still work alongside the derived one.
    service.valid_api_key = "alpha"
    assert service.validate_api_key("alpha") is True
    assert service.validate_api_key(derived) is True

    monkeypatch.delenv("MANOR_OAUTH_CLIENT_SECRET")
    assert service.validate_api_key(derived) is False
