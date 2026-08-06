"""The integration API must derive the tenant from the credential, never from
a caller-supplied parameter.

Regression coverage for the cross-tenant read: the API key is a single shared
secret, so before these rules existed anyone holding it could name any
entity_id in the query string and read that tenant's meetings.
"""
import pytest
from fastapi import HTTPException

from api.routers.integration import _resolve_entity_id


# --- unscoped credential: authenticates, but reaches no tenant ---------------

def test_unscoped_api_key_is_refused_even_with_entity_id():
    auth = {"authenticated": True, "auth_method": "api_key", "trusted_service": False}
    with pytest.raises(HTTPException) as exc:
        _resolve_entity_id(auth, "victim-entity")
    assert exc.value.status_code == 403


def test_unscoped_api_key_is_refused_without_entity_id():
    auth = {"authenticated": True, "auth_method": "api_key", "trusted_service": False}
    with pytest.raises(HTTPException) as exc:
        _resolve_entity_id(auth, None)
    assert exc.value.status_code == 403


# --- bound credential: the binding wins over the query string ---------------

def test_bound_credential_ignores_absent_parameter():
    auth = {"entity_id": "entity-a", "trusted_service": False}
    assert _resolve_entity_id(auth, None) == "entity-a"


def test_bound_credential_accepts_matching_parameter():
    auth = {"entity_id": "entity-a", "trusted_service": False}
    assert _resolve_entity_id(auth, "entity-a") == "entity-a"


def test_bound_credential_rejects_mismatched_parameter():
    """The core of the fix: a bound credential cannot be redirected."""
    auth = {"entity_id": "entity-a", "trusted_service": False}
    with pytest.raises(HTTPException) as exc:
        _resolve_entity_id(auth, "entity-b")
    assert exc.value.status_code == 403


def test_binding_wins_even_when_credential_is_also_trusted():
    auth = {"entity_id": "entity-a", "trusted_service": True}
    with pytest.raises(HTTPException) as exc:
        _resolve_entity_id(auth, "entity-b")
    assert exc.value.status_code == 403


def test_jwt_entity_id_is_coerced_to_string():
    """Local-auth JWTs carry a numeric entity_id (see _stable_entity_id)."""
    auth = {"entity_id": 1234567, "trusted_service": False}
    assert _resolve_entity_id(auth, "1234567") == "1234567"


# --- trusted service credential: may name the entity it acts for ------------

def test_trusted_service_may_name_an_entity():
    auth = {"trusted_service": True}
    assert _resolve_entity_id(auth, "entity-b") == "entity-b"


def test_trusted_service_still_needs_an_entity_id():
    auth = {"trusted_service": True}
    with pytest.raises(HTTPException) as exc:
        _resolve_entity_id(auth, None)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_entity_id_is_not_an_entity(blank):
    auth = {"trusted_service": True}
    with pytest.raises(HTTPException) as exc:
        _resolve_entity_id(auth, blank)
    assert exc.value.status_code == 400


def test_blank_binding_does_not_count_as_bound():
    """A whitespace-only binding must not silently authorize the caller."""
    auth = {"entity_id": "   ", "trusted_service": False}
    with pytest.raises(HTTPException) as exc:
        _resolve_entity_id(auth, "entity-b")
    assert exc.value.status_code == 403
