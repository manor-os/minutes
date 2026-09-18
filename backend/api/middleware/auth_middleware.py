"""
Authentication middleware that supports both JWT tokens and API keys
"""
from typing import Optional, Union
from fastapi import HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.routers.auth import get_current_user
from api.services.api_key_service import verify_api_key

security = HTTPBearer(auto_error=False)

from api.config.edition import AUTH_MODE


def _ensure_entity_id(user_dict: dict) -> dict:
    """Ensure entity_id exists as a string. For local auth mode,
    generate a stable UUID-like entity_id from email if missing."""
    eid = user_dict.get('entity_id')
    if eid is not None and str(eid).strip():
        user_dict['entity_id'] = str(eid)
        return user_dict

    # Generate from email/sub
    seed = (user_dict.get('email') or user_dict.get('sub')
            or user_dict.get('user_name') or '')
    if seed:
        import hashlib
        user_dict['entity_id'] = hashlib.sha256(seed.lower().strip().encode()).hexdigest()[:12]
    return user_dict


async def get_authenticated_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> dict:
    """
    Dependency that accepts either JWT token (Bearer) or API key

    Priority:
    1. API Key (X-API-Key header)
    2. JWT Token (Authorization: Bearer <token>)
    """
    # Try API key first
    if x_api_key:
        try:
            api_key_info = await verify_api_key(x_api_key)
            result = {
                **api_key_info,
                "auth_method": "api_key",
            }
            return _ensure_entity_id(result)
        except HTTPException:
            pass  # API key invalid, try JWT

    # Try JWT token
    if authorization:
        try:
            try:
                scheme, token = authorization.split()
                if scheme.lower() == "bearer":
                    jwt_user = await get_current_user(authorization=authorization)
                    result = {
                        **jwt_user,
                        "auth_method": "jwt",
                    }
                    return _ensure_entity_id(result)
            except ValueError:
                pass
        except HTTPException:
            pass  # JWT invalid

    # Neither authentication method worked
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide either X-API-Key header or Authorization: Bearer <token>"
    )

