"""
Manor AI OAuth2 / OIDC client for Cloud edition.

Flow:
1. Backend builds the Manor authorize URL and redirects the browser there.
2. Manor authenticates the user and redirects back to the callback endpoint
   with an authorization code.
3. Backend exchanges the code for an access token at Manor's token endpoint.
4. Backend calls Manor's userinfo endpoint to fetch the Manor user identity.
5. Backend calls Manor's subscription endpoint to check whether the user has
   an active "minutes" subscription. Login is rejected when they do not.

Endpoints, client credentials, and the redirect URI are all configured via
env vars — see `.env.example`. The defaults assume Manor exposes a standard
OAuth2 surface; adjust the *_PATH vars if Manor's routes differ.
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
import jwt
from loguru import logger

# --- Config from env -------------------------------------------------------

MANOR_BASE_URL = os.getenv("MANOR_BASE_URL", "https://app.manorai.xyz").rstrip("/")
MANOR_CLIENT_ID = os.getenv("MANOR_CLIENT_ID", "")
MANOR_CLIENT_SECRET = os.getenv("MANOR_CLIENT_SECRET", "")
MANOR_REDIRECT_URI = os.getenv("MANOR_REDIRECT_URI", "")
MANOR_OAUTH_SCOPE = os.getenv("MANOR_OAUTH_SCOPE", "openid profile email subscriptions")

MANOR_AUTHORIZE_PATH = os.getenv("MANOR_AUTHORIZE_PATH", "/oauth/authorize")
MANOR_TOKEN_PATH = os.getenv("MANOR_TOKEN_PATH", "/oauth/token")
MANOR_USERINFO_PATH = os.getenv("MANOR_USERINFO_PATH", "/api/me")
MANOR_SUBSCRIPTION_PATH = os.getenv(
    "MANOR_SUBSCRIPTION_PATH", "/api/subscriptions/minutes"
)
# Product key Manor uses to identify the minutes subscription
MANOR_MINUTES_PRODUCT = os.getenv("MANOR_MINUTES_PRODUCT", "minutes")

# State token is signed with the existing JWT secret so we do not need a
# separate secret to maintain.
_STATE_SECRET = os.getenv("JWT_SECRET", "meeting-note-taker-secret-key-change-in-production")
_STATE_ALG = "HS256"
_STATE_TTL_SECONDS = 600  # 10 minutes is plenty for an OAuth round trip

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def is_configured() -> bool:
    """Return True if Manor OAuth is fully configured."""
    return bool(MANOR_BASE_URL and MANOR_CLIENT_ID and MANOR_CLIENT_SECRET and MANOR_REDIRECT_URI)


# --- State token (CSRF + post-login redirect) ------------------------------

def build_state(post_login_redirect: str = "") -> str:
    """Sign a short-lived state token used to defeat CSRF on the callback
    and to remember where to send the user once login succeeds."""
    payload = {
        "nonce": secrets.token_urlsafe(16),
        "redirect": post_login_redirect or "",
        "exp": datetime.utcnow() + timedelta(seconds=_STATE_TTL_SECONDS),
        "iat": datetime.utcnow(),
        "purpose": "manor_oauth_state",
    }
    return jwt.encode(payload, _STATE_SECRET, algorithm=_STATE_ALG)


def parse_state(state: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(state, _STATE_SECRET, algorithms=[_STATE_ALG])
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid Manor OAuth state: {e}")
        return None
    if payload.get("purpose") != "manor_oauth_state":
        return None
    return payload


# --- OAuth steps -----------------------------------------------------------

def build_authorize_url(state: str) -> str:
    params = {
        "client_id": MANOR_CLIENT_ID,
        "redirect_uri": MANOR_REDIRECT_URI,
        "response_type": "code",
        "scope": MANOR_OAUTH_SCOPE,
        "state": state,
    }
    return f"{MANOR_BASE_URL}{MANOR_AUTHORIZE_PATH}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> Optional[Dict[str, Any]]:
    """Exchange an authorization code for an access token."""
    url = f"{MANOR_BASE_URL}{MANOR_TOKEN_PATH}"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": MANOR_REDIRECT_URI,
        "client_id": MANOR_CLIENT_ID,
        "client_secret": MANOR_CLIENT_SECRET,
    }
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.post(url, data=data)
            if resp.status_code >= 400:
                logger.error(f"Manor token exchange failed ({resp.status_code}): {resp.text[:300]}")
                return None
            return resp.json()
    except httpx.HTTPError as e:
        logger.error(f"Manor token exchange transport error: {e}")
        return None


def fetch_userinfo(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch the Manor user profile."""
    url = f"{MANOR_BASE_URL}{MANOR_USERINFO_PATH}"
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
            if resp.status_code >= 400:
                logger.error(f"Manor userinfo failed ({resp.status_code}): {resp.text[:300]}")
                return None
            return resp.json()
    except httpx.HTTPError as e:
        logger.error(f"Manor userinfo transport error: {e}")
        return None


def check_minutes_subscription(access_token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Return (active, raw_subscription_object).

    The "active" flag is true when Manor reports an active entitlement for the
    minutes product. The shape of Manor's response is normalised here so that
    callers do not need to care about the exact field names.
    """
    url = f"{MANOR_BASE_URL}{MANOR_SUBSCRIPTION_PATH}"
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"product": MANOR_MINUTES_PRODUCT},
            )
            if resp.status_code == 404:
                # Manor returns 404 when there is no subscription record
                return False, None
            if resp.status_code >= 400:
                logger.error(f"Manor subscription check failed ({resp.status_code}): {resp.text[:300]}")
                return False, None
            sub = resp.json()
    except httpx.HTTPError as e:
        logger.error(f"Manor subscription check transport error: {e}")
        return False, None

    # Manor's response may be either {"active": true, ...} or {"status": "active"}
    # or wrap the subscription in a list — handle the common shapes.
    if isinstance(sub, list):
        sub = sub[0] if sub else None
    if not isinstance(sub, dict):
        return False, None

    if sub.get("active") is True:
        return True, sub
    status = (sub.get("status") or "").lower()
    if status in ("active", "trialing"):
        return True, sub
    return False, sub
