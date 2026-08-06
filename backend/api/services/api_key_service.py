"""
API Key service for authenticating external services (like Manor AI)

The API key is a single shared secret, so on its own it identifies *a caller*
and never *a tenant*. Two env vars turn it into a scoped credential:

  MEETING_NOTE_TAKER_API_KEY_ENTITY_ID
      Bind the key to exactly one entity. Requests may only touch that entity.

  MEETING_NOTE_TAKER_API_KEY_TRUSTED=true
      Mark the key as a trusted service-to-service credential (e.g. the Manor
      backend) that is allowed to name the entity it acts for.

With neither set the key can authenticate but cannot reach any tenant's data.
That is deliberate: an unscoped shared secret must not be a master key.
"""
import hmac
import os
from typing import Optional
from fastapi import HTTPException, Security, Header
from fastapi.security import APIKeyHeader
from loguru import logger

# API Key header name
API_KEY_HEADER = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)

_TRUTHY = ("1", "true", "yes", "on")


class APIKeyService:
    """Service for managing and validating API keys"""

    def __init__(self):
        # Get API key from environment variable
        self.valid_api_key = os.getenv("MEETING_NOTE_TAKER_API_KEY", "")
        # Tenant scope for this key (see module docstring).
        self.entity_id = (os.getenv("MEETING_NOTE_TAKER_API_KEY_ENTITY_ID") or "").strip()
        self.trusted_service = (
            os.getenv("MEETING_NOTE_TAKER_API_KEY_TRUSTED") or ""
        ).strip().lower() in _TRUTHY

        if not self.valid_api_key:
            logger.warning("MEETING_NOTE_TAKER_API_KEY not set. API key authentication will be disabled.")
        else:
            logger.info(f"API key authentication enabled. Key: {self.valid_api_key[:8]}...")
            if self.entity_id:
                logger.info(f"API key is scoped to entity {self.entity_id}")
            elif self.trusted_service:
                logger.info("API key is a trusted service credential and may act for any entity")
            else:
                logger.warning(
                    "API key has no tenant scope: set MEETING_NOTE_TAKER_API_KEY_ENTITY_ID to bind it "
                    "to one entity, or MEETING_NOTE_TAKER_API_KEY_TRUSTED=true for service-to-service "
                    "use. Until then it cannot read any tenant's data."
                )

    def validate_api_key(self, api_key: Optional[str]) -> bool:
        """
        Validate API key

        Args:
            api_key: API key to validate

        Returns:
            True if valid, False otherwise
        """
        if not self.valid_api_key:
            # If no API key is configured, reject all requests
            return False

        if not api_key:
            return False

        # Constant-time comparison so a wrong key cannot be recovered byte by byte.
        return hmac.compare_digest(api_key, self.valid_api_key)

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
    info = {
        "authenticated": True,
        "auth_method": "api_key",
        "trusted_service": api_key_service.trusted_service,
    }
    # Only set entity_id when the key is bound to one; an unscoped key must not
    # inherit a tenant from anywhere else.
    if api_key_service.entity_id:
        info["entity_id"] = api_key_service.entity_id
    return info

