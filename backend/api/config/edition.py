"""
Central edition configuration. Single source of truth for feature flags.
EDITION env var: "community" (default, open-source) or "cloud" (SaaS)
"""
import os

EDITION = os.getenv("EDITION", "community")
IS_CLOUD = EDITION == "cloud"
IS_COMMUNITY = EDITION == "community"

# All editions support local auth. Cloud edition additionally exposes Manor
# AI SSO ("Sign in with Manor") so subscribers can drop in with their
# existing Manor account and have usage billed against Manor credits.
AUTH_MODE = "local"
ENABLE_MCP = IS_CLOUD
ENABLE_USAGE_REPORTING = IS_CLOUD  # Report to Manor Java backend
ENABLE_TEAMS = IS_CLOUD
ENABLE_ANALYTICS = IS_CLOUD
ENABLE_MANOR_SSO = IS_CLOUD
ENABLE_MANOR_BILLING = IS_CLOUD

# Where to redirect the browser after a successful Manor OAuth callback.
# The minutes JWT is appended as `?token=...`.
MANOR_LOGIN_SUCCESS_REDIRECT = os.getenv(
    "MANOR_LOGIN_SUCCESS_REDIRECT", "http://localhost:9002/auth/manor"
)
# Where to redirect when login fails. The reason is appended as `?error=...`.
MANOR_LOGIN_FAILURE_REDIRECT = os.getenv(
    "MANOR_LOGIN_FAILURE_REDIRECT", "http://localhost:9002/auth/manor"
)
