"""
Central edition configuration. Single source of truth for feature flags.
EDITION env var: "community" (default, open-source) or "cloud" (SaaS)
"""
import os

EDITION = os.getenv("EDITION", "community")
IS_CLOUD = EDITION == "cloud"
IS_COMMUNITY = EDITION == "community"

# All editions now use local auth (Manor proxy auth has been removed)
AUTH_MODE = "local"
ENABLE_MCP = IS_CLOUD
ENABLE_USAGE_REPORTING = IS_CLOUD  # Report to Manor Java backend
ENABLE_TEAMS = IS_CLOUD
ENABLE_ANALYTICS = IS_CLOUD
