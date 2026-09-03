"""
Billing gateway: route each LLM operation by auth type and keep Manor-credit
and BYO-key billing strictly separated.

- classify(user)                  -> "manor" | "byo"
- ensure_credit(entity_id, ...)   -> raises CreditExhaustedError when Manor says
                                     the entity may not spend (or there is no entity)

Manor accounts are never billed from Minutes itself. Every LLM call for them
goes through the Manor LLM gateway (see ``llm_config.resolve_llm``), which
debits the entity's credits as it runs the provider call. ``ensure_credit`` is
only a preflight against that same gateway so expensive work (an upload that
still has to be transcribed) is refused up front instead of failing after
transcription.
"""
from typing import Optional

import httpx
from loguru import logger

from api.services.llm_config import (
    ManorGatewayNotConfigured,
    get_manor_gateway_url,
    manor_gateway_headers,
)


class CreditExhaustedError(Exception):
    """Manor entity is out of credit, or unbillable (no entity)."""


def classify(user: dict) -> str:
    """Return "manor" for Manor-SSO-backed requests, else "byo".

    Manor and Google logins both authenticate through the Manor backend and
    carry a Manor entity_id (auth_source "manor"/"google"), so both bill the
    Manor credit pool. Locally-registered users (auth_source "local", or any
    request without a Manor auth_source) bring their own key.
    """
    return "manor" if (user or {}).get("auth_source") in ("manor", "google") else "byo"


def _manor_credit_available(entity_id, user_id=None) -> bool:
    """Ask the Manor gateway whether the entity may spend credits right now.

    GET {MANOR_API_BASE_URL}/api/v1/llm/credit with Minutes' client credentials:
      200            -> True
      402            -> False (out of credit)
      anything else / network error -> True (FAIL OPEN: a transient Manor
                        outage must not block users; the gateway enforces the
                        gate again on the actual LLM call).
    """
    try:
        headers = manor_gateway_headers(entity_id=entity_id, user_id=user_id)
    except ManorGatewayNotConfigured as exc:
        logger.warning(f"Manor credit preflight skipped: {exc}")
        return True
    try:
        resp = httpx.get(f"{get_manor_gateway_url()}/credit", headers=headers, timeout=5.0)
    except Exception as exc:
        logger.warning(f"Manor credit preflight failed for entity {entity_id}, failing open: {exc}")
        return True
    if resp.status_code == 200:
        return True
    if resp.status_code == 402:
        return False
    logger.warning(
        f"Manor credit preflight returned {resp.status_code} for entity {entity_id}, failing open"
    )
    return True


def ensure_credit(entity_id, user_id: Optional[str] = None, auth=None) -> None:
    """
    Gate a Manor-path operation on available credit.

    Raises CreditExhaustedError when Manor reports the entity is out of credit
    OR when there is no entity_id (a Manor request that cannot be attributed
    must not run — the gateway would reject it anyway).

    Fails OPEN on a transient Manor outage so users are not punished for it.

    `auth` is a test seam: when provided, its `check_credit_available(entity_id)`
    is used instead of the live gateway preflight.
    """
    if not entity_id:
        raise CreditExhaustedError("Manor request without entity_id cannot be billed")
    available = (
        auth.check_credit_available(entity_id)
        if auth is not None
        else _manor_credit_available(entity_id, user_id=user_id)
    )
    if not available:
        raise CreditExhaustedError(f"Entity {entity_id} is out of credit")


def is_credit_exhausted_error(exc: BaseException) -> bool:
    """True when an OpenAI-SDK error came from the Manor gateway's credit gate.

    The gateway answers a plain HTTP 402 before streaming starts, and an
    OpenAI-style ``{"error": {"code": 402}}`` event once a stream is open;
    the SDK surfaces those as ``APIStatusError`` / ``APIError`` respectively.
    """
    if getattr(exc, "status_code", None) == 402:
        return True
    code = getattr(exc, "code", None)
    if code in (402, "402"):
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        if err.get("code") in (402, "402") or err.get("type") == "insufficient_credit":
            return True
    return False
