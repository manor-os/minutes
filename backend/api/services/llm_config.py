"""
Shared LLM configuration for the meeting-note-taker service.

Two ways an LLM call can be routed:

* ``manor``  – the request belongs to a Manor account. Minutes never holds a
  provider key for these users: the OpenAI-compatible client points at the
  Manor LLM gateway (``{MANOR_API_BASE_URL}/api/v1/llm``), authenticating with
  the OAuth client credentials Manor issued to Minutes and naming the entity
  / user to bill. Manor resolves the model, runs the provider call and debits
  the entity's credits itself.
* ``byo``    – a locally registered user. Their own ``llm_api_key`` /
  ``llm_base_url`` / ``llm_model`` from Settings are used and they pay the
  provider directly.

The server-wide ``OPENROUTER_API_KEY`` / ``OPENAI_API_KEY`` remain for
community deployments and for STT, which is not routed through Manor.
"""
import os
from typing import Optional
from urllib.parse import urlsplit

from openai import OpenAI

_DEFAULT_MODEL = "moonshotai/kimi-k2.5"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Map frontend alias values to actual API model IDs
_MODEL_ALIASES: dict = {
    "gpt4o": "gpt-4o",
    "gpt4o-mini": "gpt-4o-mini",
    "claude-sonnet": "anthropic/claude-sonnet-4-5",
    "claude-opus": "anthropic/claude-opus-4-5",
    "gemini": "google/gemini-pro",
    "gemini-flash": "google/gemini-flash-1.5",
    "deepseek": "deepseek/deepseek-chat",
    "kimi": "moonshotai/kimi-k2.5",
}


def get_openrouter_api_key() -> str:
    return (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def get_openrouter_base_url() -> str:
    # When OPENROUTER_API_KEY is set, honour OPENROUTER_BASE_URL / LLM_BASE_URL.
    # When falling back to OPENAI_API_KEY, use OpenRouter default (the OpenAI key
    # works fine through OpenRouter) — but do NOT use LLM_BASE_URL because it may
    # point at a different provider (e.g. DeepSeek) that rejects the OpenAI key.
    if os.getenv("OPENROUTER_API_KEY"):
        return (
            os.getenv("OPENROUTER_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or _DEFAULT_BASE_URL
        ).rstrip("/")
    return (os.getenv("OPENROUTER_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")


def get_llm_model() -> str:
    """Return the LLM model to use. Auto-detects appropriate model for the provider."""
    raw = (os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL") or "").strip()
    if raw:
        # Resolve frontend alias to actual model ID if needed
        return _MODEL_ALIASES.get(raw, raw)

    # Auto-detect: if using OpenAI key directly, default to gpt-4o-mini
    api_key = get_openrouter_api_key()
    if api_key and api_key.startswith("sk-") and not api_key.startswith("sk-or-"):
        explicit_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENROUTER_BASE_URL")
        if not explicit_url:
            return "gpt-4o-mini"  # Default for OpenAI direct

    return _DEFAULT_MODEL


def get_openrouter_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAI:
    """Return an OpenAI-compatible client. Uses OpenRouter by default,
    but auto-detects OpenAI keys and routes to api.openai.com instead.

    Args:
        api_key: Override the API key (e.g. per-user key from DB).
        base_url: Override the base URL (e.g. per-user custom endpoint from DB).
    """
    resolved_key = api_key or get_openrouter_api_key()
    resolved_url = base_url or get_openrouter_base_url()

    # Auto-detect: if key looks like an OpenAI key (sk-..., not sk-or-...)
    # and no explicit base URL override, use OpenAI directly
    if not base_url and resolved_key and resolved_key.startswith("sk-") and not resolved_key.startswith("sk-or-"):
        explicit_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENROUTER_BASE_URL")
        if not explicit_url:
            resolved_url = "https://api.openai.com/v1"

    return OpenAI(api_key=resolved_key, base_url=resolved_url)


# ── Manor LLM gateway ──


def get_manor_api_base_url() -> str:
    """Origin of the Manor API, e.g. ``https://app.manorai.xyz``.

    ``MANOR_API_BASE_URL`` wins; otherwise it is derived from the OAuth token
    URL the cloud edition already configures, so no new variable is required
    for existing deployments.
    """
    explicit = (os.getenv("MANOR_API_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    token_url = (os.getenv("MANOR_OAUTH_TOKEN_URL") or "").strip()
    if token_url:
        parts = urlsplit(token_url)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    return "https://app.manorai.xyz"


def get_manor_gateway_url() -> str:
    """OpenAI-compatible base URL of the Manor gateway (``.../api/v1/llm``)."""
    return f"{get_manor_api_base_url()}/api/v1/llm"


class ManorGatewayNotConfigured(Exception):
    """Minutes has no Manor OAuth client credentials to call the gateway with."""


def get_manor_client_credentials() -> tuple:
    """(client_id, client_secret) Minutes uses to call Manor on a user's behalf."""
    client_id = (os.getenv("MANOR_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("MANOR_OAUTH_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise ManorGatewayNotConfigured(
            "MANOR_OAUTH_CLIENT_ID / MANOR_OAUTH_CLIENT_SECRET must be set to route "
            "Manor accounts through the Manor LLM gateway."
        )
    return client_id, client_secret


def manor_gateway_headers(*, entity_id, user_id=None, business_type: Optional[str] = None) -> dict:
    """Headers that authenticate Minutes to the gateway and name who is billed."""
    client_id, client_secret = get_manor_client_credentials()
    headers = {
        "X-Manor-Client-Id": client_id,
        "X-Manor-Client-Secret": client_secret,
        "X-Manor-Entity-Id": str(entity_id),
    }
    if user_id:
        headers["X-Manor-User-Id"] = str(user_id)
    if business_type:
        headers["X-Manor-Business-Type"] = business_type
    return headers


def get_manor_gateway_client(*, entity_id, user_id=None, business_type: Optional[str] = None) -> OpenAI:
    """OpenAI-compatible client whose every call is billed to a Manor entity."""
    if not entity_id:
        raise ValueError("entity_id is required to route a call through the Manor gateway")
    return OpenAI(
        # The gateway authenticates with the client headers; the SDK still
        # insists on a non-empty key, so send a placeholder bearer.
        api_key="manor-gateway",
        base_url=get_manor_gateway_url(),
        default_headers=manor_gateway_headers(
            entity_id=entity_id, user_id=user_id, business_type=business_type,
        ),
    )


class MissingKeyError(Exception):
    """A BYO-key user has no LLM API key configured."""


def resolve_llm(*, route: str, user_keys: Optional[dict] = None, manor_ctx: Optional[dict] = None):
    """
    Return (OpenAI-compatible client, model_name) for the given route.

    route == "manor": client pointed at the Manor LLM gateway, billed to
                      ``manor_ctx["entity_id"]`` (with optional ``user_id``
                      and ``business_type`` for attribution).
    route == "byo":   the user's own llm_api_key / llm_base_url / llm_model.
                      Raises MissingKeyError if no llm_api_key is set.
    """
    if route == "byo":
        keys = user_keys or {}
        api_key = (keys.get("llm_api_key") or "").strip()
        if not api_key:
            raise MissingKeyError("No LLM API key configured. Add one in Settings.")
        base_url = (keys.get("llm_base_url") or "").strip() or None
        model = (keys.get("llm_model") or "").strip() or get_llm_model()
        return get_openrouter_client(api_key=api_key, base_url=base_url), model

    ctx = manor_ctx or {}
    client = get_manor_gateway_client(
        entity_id=ctx.get("entity_id"),
        user_id=ctx.get("user_id"),
        business_type=ctx.get("business_type"),
    )
    return client, get_llm_model()
