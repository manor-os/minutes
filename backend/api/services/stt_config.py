"""Resolve transcription credentials without crossing account boundaries."""

import os


def resolve_stt_config(*, manor_managed: bool, user_config: dict | None = None) -> dict:
    # Hosted/Manor accounts always use the deployment's audio credentials.
    # User settings are only meaningful for a local community account.
    config = {} if manor_managed else (user_config or {})
    user_key = (config.get("stt_api_key") or "").strip()
    server_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    base_url = (
        (config.get("stt_base_url") or "").strip() if user_key else ""
    ) or (os.getenv("OPENAI_BASE_URL") or "").strip() or None
    return {
        "api_key": user_key or server_key,
        "base_url": base_url,
        "use_local": os.getenv("STT_MODE", "cloud") == "local",
    }
