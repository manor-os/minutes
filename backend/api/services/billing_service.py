"""
Billing gateway: route each LLM operation by auth type and keep Manor-credit
and BYO-key billing strictly separated.

- classify(user)         -> "manor" | "byo"
- ensure_credit(entity)  -> raises CreditExhaustedError if locked / no entity
- report_usage(...)      -> fire-and-forget POST to Manor Java billing endpoint
"""
import os
from typing import Optional

import httpx
from loguru import logger


class CreditExhaustedError(Exception):
    """Manor entity is locked / out of credit, or unbillable (no entity)."""


def classify(user: dict) -> str:
    """Return "manor" for Manor-SSO-backed requests, else "byo".

    Manor and Google logins both authenticate through the Manor backend and
    carry a Manor entity_id (auth_source "manor"/"google"), so both bill the
    Manor credit pool. Locally-registered users (auth_source "local", or any
    request without a Manor auth_source) bring their own key.
    """
    return "manor" if (user or {}).get("auth_source") in ("manor", "google") else "byo"


def _entity_has_credit(entity_id) -> bool:
    """Query Manor's MySQL `entity` table for the locked flag.

    locked = 1 / '1'  -> suspended / out of credit  -> False (block).
    Entity not found  -> False (cannot bill an unknown entity).
    Any connection / query error -> True (FAIL OPEN: don't punish users for a
    transient Manor-DB outage).

    Uses the same MANOR_AI_MYSQL_* config the upload endpoint already relies on
    to look up sys_user, so no new infrastructure is required.
    """
    import pymysql
    conn = None
    try:
        conn = pymysql.connect(
            host=os.getenv("MANOR_AI_MYSQL_HOST") or os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MANOR_AI_MYSQL_PORT") or os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MANOR_AI_MYSQL_USERNAME") or os.getenv("MYSQL_USERNAME", "root"),
            password=os.getenv("MANOR_AI_MYSQL_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MANOR_AI_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE", "manor"),
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT locked FROM entity WHERE entity_id = %s LIMIT 1", (entity_id,))
            row = cur.fetchone()
        if not row:
            return False
        locked = row.get("locked")
        return not (locked == 1 or locked == "1")
    except Exception as exc:
        logger.warning(f"Credit check failed for entity {entity_id}, failing open: {exc}")
        return True
    finally:
        if conn is not None:
            conn.close()


def ensure_credit(entity_id, auth=None) -> None:
    """
    Gate a Manor-path operation on available credit.

    Raises CreditExhaustedError when the entity is locked OR when there is no
    entity_id (a Manor request that cannot be attributed must not run on the
    shared key — that would leak cost across account types).

    Fails OPEN only on a transient backend error: the credit check returns True
    when its DB read raises, so a Manor-DB outage does not block users.

    `auth` is a test seam: when provided, its `check_credit_available(entity_id)`
    is used instead of the live Manor-DB lookup.
    """
    if not entity_id:
        raise CreditExhaustedError("Manor request without entity_id cannot be billed")
    available = (
        auth.check_credit_available(entity_id)
        if auth is not None
        else _entity_has_credit(entity_id)
    )
    if not available:
        raise CreditExhaustedError(f"Entity {entity_id} is out of credit")


def report_usage(*, entity_id, user_id: Optional[str], client_name: Optional[str],
                 input_tokens: int, output_tokens: int, business_type: str) -> None:
    """Fire-and-forget: POST token usage to Manor Java /business/tokenLog/record."""
    total = (input_tokens or 0) + (output_tokens or 0)
    if total <= 0 or not entity_id:
        return
    java_host = (os.getenv("JAVA_HOST") or os.getenv("MANOR_BACKEND_URL", "http://localhost:8070")).rstrip("/")
    payload = {
        "entityId": str(entity_id),
        "userId": str(user_id) if user_id else None,
        "clientName": client_name or None,
        "inputToken": int(input_tokens or 0),
        "outputToken": int(output_tokens or 0),
        "totalToken": int(total),
        "trackedAgentKey": "meeting_note_taker",
        "businessType": business_type,
    }
    try:
        httpx.post(f"{java_host}/business/tokenLog/record", json=payload, timeout=5.0)
    except Exception as exc:
        logger.warning(f"Failed to report token usage to Manor Java: {exc}")
