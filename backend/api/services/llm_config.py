"""
Shared LLM configuration for the meeting-note-taker service.

Uses the same OpenRouter key & base URL as manor-multi-agent so all
sub-projects share a single billing path.  Falls back to OPENAI_API_KEY
for local dev environments that don't have OpenRouter configured.
"""
import os
from typing import Optional

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
