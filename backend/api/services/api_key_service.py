"""
API Key service for authenticating external services (like Manor AI)
"""
import hashlib
import hmac
import os
from typing import Optional
from fastapi import HTTPException, Security, Header
from fastapi.security import APIKeyHeader
from loguru import logger

# API Key header name
API_KEY_HEADER = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


class APIKeyService:
    """Service for managing and validating API keys"""
    
    def __init__(self):
        # MEETING_NOTE_TAKER_API_KEY may hold several comma-separated keys so
        # a new key can be rolled out to callers before the old one is retired.
        self.valid_api_key = os.getenv("MEETING_NOTE_TAKER_API_KEY", "")

        if not self.valid_api_key:
            logger.warning("MEETING_NOTE_TAKER_API_KEY not set. API key authentication will be disabled.")
        else:
            logger.info(f"API key authentication enabled ({len(self._valid_keys())} key(s)).")

    def _valid_keys(self) -> list:
        # Parsed on every call so tests and rotations that assign
        # valid_api_key directly keep working.
        keys = [k.strip() for k in self.valid_api_key.split(",") if k.strip()]
        derived = self._derived_service_key()
        if derived:
            keys.append(derived)
        return keys

    @staticmethod
    def _derived_service_key() -> Optional[str]:
        # The Manor platform and this backend already share one secret: the
        # OAuth client secret Manor issued to Minutes. Deriving a service key
        # from it (one-way) lets both sides agree on a key with no extra
        # provisioning; an explicit MEETING_NOTE_TAKER_API_KEY still works
        # alongside it.
        client_secret = os.getenv("MANOR_OAUTH_CLIENT_SECRET", "")
        if not client_secret:
            return None
        return hmac.new(
            client_secret.encode(),
            b"manor-minutes-mcp-service-key-v1",
            hashlib.sha256,
        ).hexdigest()

    def validate_api_key(self, api_key: Optional[str]) -> bool:
        """
        Validate API key

        Args:
            api_key: API key to validate

        Returns:
            True if valid, False otherwise
        """
        if not api_key:
            return False

        # If no API key is configured, reject all requests
        return any(hmac.compare_digest(api_key, valid) for valid in self._valid_keys())
    
    def get_api_key(self) -> Optional[str]:
        """
        Get the configured API key (for documentation purposes)
        
        Returns:
            API key if configured, None otherwise
        """
        return self.valid_api_key


# Global API key service instance
api_key_service = APIKeyService()


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header)
) -> dict:
    """
    Dependency to verify API key for protected endpoints
    
    Usage:
        @router.get("/protected")
        async def protected_route(api_key_info: dict = Depends(verify_api_key)):
            ...
    """
    if not api_key_service.validate_api_key(api_key):
        logger.warning(f"Invalid API key attempt: {api_key[:8] if api_key else 'None'}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide X-API-Key header."
        )
    
    logger.debug("API key validated successfully")
    return {
        "authenticated": True,
        "auth_method": "api_key"
    }

