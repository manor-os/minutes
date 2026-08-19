"""Dependency for gating cloud-only endpoints."""
from fastapi import HTTPException
from api.config.edition import IS_CLOUD

async def require_cloud():
    if not IS_CLOUD:
        raise HTTPException(status_code=404, detail="Not found")
