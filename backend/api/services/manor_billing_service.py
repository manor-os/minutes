"""
Manor AI credit deduction client.

Called from the celery worker after a meeting finishes processing so the
billable usage (transcription minutes + LLM tokens) is charged against the
user's Manor credit balance.

The call is best-effort: a billing failure must never roll back a meeting
that has already been transcribed and summarised. Failures are logged so
they can be reconciled out-of-band.
"""
import os
from typing import Any, Dict, Optional

import httpx
from loguru import logger

MANOR_BASE_URL = os.getenv("MANOR_BASE_URL", "https://app.manorai.xyz").rstrip("/")
MANOR_BILLING_PATH = os.getenv("MANOR_BILLING_PATH", "/api/credits/charge")
# Service-to-service API key for billing calls. Distinct from MANOR_CLIENT_SECRET
# (which is the OAuth client secret) so the two surfaces can be rotated separately.
MANOR_SERVICE_API_KEY = os.getenv("MANOR_SERVICE_API_KEY", "")
MANOR_MINUTES_PRODUCT = os.getenv("MANOR_MINUTES_PRODUCT", "minutes")

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def is_configured() -> bool:
    return bool(MANOR_BASE_URL and MANOR_SERVICE_API_KEY)


def charge_credits(
    manor_user_id: str,
    transcription_minutes: float,
    input_tokens: int,
    output_tokens: int,
    meeting_id: Optional[str] = None,
) -> bool:
    """Charge the Manor account for one completed meeting.

    Returns True on a successful 2xx response. Does not raise — callers are
    expected to log and continue regardless.
    """
    if not is_configured():
        logger.debug("Manor billing not configured — skipping charge")
        return False
    if not manor_user_id:
        logger.debug("No manor_user_id on this meeting — skipping charge")
        return False

    url = f"{MANOR_BASE_URL}{MANOR_BILLING_PATH}"
    payload: Dict[str, Any] = {
        "user_id": manor_user_id,
        "product": MANOR_MINUTES_PRODUCT,
        "usage": {
            "transcription_minutes": round(float(transcription_minutes or 0), 4),
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
        },
    }
    if meeting_id:
        # Idempotency key so retries don't double-charge.
        payload["idempotency_key"] = f"meeting:{meeting_id}"

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {MANOR_SERVICE_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code >= 400:
                logger.error(
                    f"Manor credit charge failed ({resp.status_code}) for user={manor_user_id} "
                    f"meeting={meeting_id}: {resp.text[:300]}"
                )
                return False
            logger.info(
                f"Charged Manor credits user={manor_user_id} meeting={meeting_id} "
                f"minutes={transcription_minutes} in={input_tokens} out={output_tokens}"
            )
            return True
    except httpx.HTTPError as e:
        logger.error(f"Manor credit charge transport error for user={manor_user_id}: {e}")
        return False
