"""
API Key service for authenticating external services (like Manor AI)
"""
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
        # Get API key from environment variable
        self.valid_api_key = os.getenv("MEETING_NOTE_TAKER_API_KEY", "")
        
        if not self.valid_api_key:
            logger.warning("MEETING_NOTE_TAKER_API_KEY not set. API key authentication will be disabled.")
        else:
            logger.info(f"API key authentication enabled. Key: {self.valid_api_key[:8]}...")
    
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
        
        # Simple string comparison (in production, use constant-time comparison)
        return api_key == self.valid_api_key
    
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

