"""
Authentication router - local auth for all editions
"""
from collections import defaultdict
from time import time
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from pydantic import BaseModel
from loguru import logger

from api.services.api_key_service import verify_api_key
from api.services.local_auth_service import (
    init_users_table, register_user, authenticate_user,
    generate_token, verify_token as verify_local_token, get_user_by_email, update_user_llm_config,
    change_password as change_password_service, delete_account as delete_account_service,
    update_user_webhook_url, seed_default_admin
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    """Register request model"""
    email: str
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request model"""
    email: str
    password: str



class LoginResponse(BaseModel):
    """Login response model"""
    success: bool
    token: Optional[str] = None
    entity_id: Optional[int] = None
    email: Optional[str] = None
    name: Optional[str] = None
    message: Optional[str] = None


# Rate limiting for registration
_register_attempts: dict = defaultdict(list)
REGISTER_RATE_LIMIT = 5  # max attempts
REGISTER_RATE_WINDOW = 3600  # per hour (seconds)


def _check_rate_limit(ip: str) -> bool:
    """Returns True if rate limit exceeded."""
    now = time()
    # Clean old entries
    _register_attempts[ip] = [t for t in _register_attempts[ip] if now - t < REGISTER_RATE_WINDOW]
    if len(_register_attempts[ip]) >= REGISTER_RATE_LIMIT:
        return True
    _register_attempts[ip].append(now)
    return False


# Rate limiting for login
_login_attempts: dict = defaultdict(list)
LOGIN_RATE_LIMIT = 10  # max attempts
LOGIN_RATE_WINDOW = 300  # per 5 minutes (seconds)


def _check_login_rate_limit(ip: str) -> bool:
    """Returns True if login rate limit exceeded."""
    now = time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < LOGIN_RATE_WINDOW]
    if len(_login_attempts[ip]) >= LOGIN_RATE_LIMIT:
        return True
    _login_attempts[ip].append(now)
    return False


@router.post("/register")
async def register(request: RegisterRequest, req: Request):
    """Register a new user (local auth mode only)"""
    client_ip = req.client.host if req.client else "unknown"
    if _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Please try again later.")

    if not request.email or not request.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = register_user(request.email, request.password, request.name)
    if not user:
        raise HTTPException(status_code=409, detail="Email already registered")

    token = generate_token({"id": str(user["id"]), "email": user["email"], "name": user["name"]})
    from api.services.local_auth_service import _stable_entity_id
    entity_id = _stable_entity_id(user["email"])
    return JSONResponse({
        "success": True,
        "token": token,
        "entity_id": entity_id,
        "email": user["email"],
        "name": user["name"],
        "message": "Registration successful"
    })


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, req: Request):
    """Login endpoint"""
    client_ip = req.client.host if req.client else "unknown"
    if _check_login_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again in 5 minutes.")

    if not request.email or not request.password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    user = authenticate_user(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = generate_token(user)
    from api.services.local_auth_service import _stable_entity_id
    entity_id = _stable_entity_id(user["email"])
    return JSONResponse({
        "success": True,
        "token": token,
        "entity_id": entity_id,
        "email": user["email"],
        "name": user["name"],
        "message": "Login successful"
    })


@router.post("/verify")
async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """
    Verify JWT token and return user information
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    payload = verify_local_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return JSONResponse({
        "success": True,
        "entity_id": payload.get("entity_id"),
        "email": payload.get("email"),
        "valid": True
    })


@router.post("/logout")
async def logout():
    """
    Logout endpoint (client-side token removal)
    """
    return JSONResponse({
        "success": True,
        "message": "Logged out successfully"
    })


# Dependency for protected routes
async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> dict:
    """
    Dependency to get current authenticated user from JWT token.

    Usage:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            entity_id = user['entity_id']
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format. Use: Bearer <token>")

    payload = verify_local_token(token)
    if payload:
        return payload

    raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.get("/me")
async def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user info from JWT token"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_local_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = get_user_by_email(payload.get("email", ""))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return JSONResponse({
        "success": True,
        "email": user["email"],
        "name": user["name"],
        "has_stt_key": bool(user.get("stt_api_key")),
        "stt_base_url": user.get("stt_base_url") or "",
        "has_llm_key": bool(user.get("llm_api_key")),
        "llm_model": user.get("llm_model") or "",
        "llm_base_url": user.get("llm_base_url") or "",
        "webhook_url": user.get("webhook_url") or "",
    })


class LlmConfigRequest(BaseModel):
    """AI configuration update request"""
    stt_api_key: Optional[str] = None
    stt_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_base_url: Optional[str] = None


@router.put("/llm-config")
async def update_llm_config(request: LlmConfigRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Update user's LLM configuration"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_local_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = payload.get("email", "")
    success = update_user_llm_config(
        email,
        stt_api_key=request.stt_api_key,
        stt_base_url=request.stt_base_url,
        llm_api_key=request.llm_api_key,
        llm_model=request.llm_model,
        llm_base_url=request.llm_base_url,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")

    return JSONResponse({"success": True, "message": "AI configuration updated"})


class WebhookRequest(BaseModel):
    """Webhook URL update request"""
    webhook_url: Optional[str] = None


@router.put("/webhook")
async def update_webhook(request: WebhookRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Update webhook URL for notifications."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_local_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Basic URL validation
    url = (request.webhook_url or "").strip()
    if url and not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Webhook URL must start with http:// or https://")

    email = payload.get("email", "")
    success = update_user_webhook_url(email, url or None)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update webhook URL")

    return JSONResponse({"success": True, "message": "Webhook URL updated"})


@router.get("/webhook")
async def get_webhook(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current webhook URL."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_local_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = payload.get("email", "")
    user = get_user_by_email(email)
    webhook_url = user.get("webhook_url", "") if user else ""

    return JSONResponse({"success": True, "webhook_url": webhook_url or ""})


class ChangePasswordRequest(BaseModel):
    """Change password request model"""
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    """Delete account request model"""
    password: str


@router.put("/change-password")
async def change_password(request: ChangePasswordRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Change password."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_local_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    email = payload.get("email", "")
    result = change_password_service(email, request.current_password, request.new_password)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to change password"))

    return JSONResponse({"success": True, "message": "Password changed successfully"})


@router.delete("/account")
async def delete_account(request: DeleteAccountRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Delete account and all data."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_local_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = payload.get("email", "")
    result = delete_account_service(email, request.password)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to delete account"))

    return JSONResponse({"success": True, "message": "Account and all data deleted successfully"})


# Initialize local users table on import (all editions now use local auth)
try:
    init_users_table()
    seed_default_admin()
except Exception as e:
    logger.warning(f"Could not init users table (DB may not be ready yet): {e}")

