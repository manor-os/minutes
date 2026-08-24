#!/usr/bin/env bash
set -euo pipefail

EXAMPLE_FILE="${ENV_EXAMPLE_FILE:-.env.example}"
OUTPUT_FILE="${ENV_OUTPUT_FILE:-.env}"
BASE_FILE="${ENV_BASE_FILE:-$OUTPUT_FILE}"

if [ ! -f "$EXAMPLE_FILE" ]; then
  echo "$EXAMPLE_FILE not found" >&2
  exit 1
fi

require_env() {
  local key="$1"
  local value="${!key:-}"

  if [ -z "$value" ]; then
    echo "$key is required for cloud deployment" >&2
    exit 1
  fi
}

set_env() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" "$OUTPUT_FILE"; then
    local tmp_file
    tmp_file="$(mktemp)"
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in
        "$key"=*) printf '%s=%s\n' "$key" "$value" ;;
        *) printf '%s\n' "$line" ;;
      esac
    done < "$OUTPUT_FILE" > "$tmp_file"
    mv "$tmp_file" "$OUTPUT_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$OUTPUT_FILE"
  fi
}

get_env_value() {
  local key="$1"
  local value="${!key:-}"

  if [ -n "$value" ]; then
    printf '%s' "$value"
    return
  fi

  if [ -f "$OUTPUT_FILE" ]; then
    value="$(grep -m 1 "^${key}=" "$OUTPUT_FILE" | cut -d= -f2- || true)"
    printf '%s' "$value"
  fi
}

if [ -f "$BASE_FILE" ]; then
  cp "$BASE_FILE" "$OUTPUT_FILE.tmp"
  mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"
else
  cp "$EXAMPLE_FILE" "$OUTPUT_FILE"
fi

require_env "MANOR_OAUTH_CLIENT_SECRET"
require_env "JWT_SECRET"

set_env "EDITION" "cloud"
set_env "PRODUCTION" "true"
set_env "VITE_API_URL" "https://minutes.manorai.xyz"
set_env "CORS_ORIGINS" "https://minutes.manorai.xyz"
set_env "MANOR_OAUTH_CLIENT_SECRET" "$(get_env_value MANOR_OAUTH_CLIENT_SECRET)"
set_env "MANOR_OAUTH_AUTHORIZE_URL" "${MANOR_OAUTH_AUTHORIZE_URL:-https://app.manorai.xyz/oauth/authorize}"
set_env "MANOR_OAUTH_TOKEN_URL" "${MANOR_OAUTH_TOKEN_URL:-https://app.manorai.xyz/api/v1/oauth/token}"
set_env "MANOR_OAUTH_REDIRECT_URI" "https://minutes.manorai.xyz/auth/manor-callback"
set_env "VITE_GOOGLE_REDIRECT_URI" "https://minutes.manorai.xyz/googleCallback"
set_env "MANOR_GOOGLE_OAUTH_URL" "${MANOR_GOOGLE_OAUTH_URL:-https://app.manorai.xyz/api/v1/auth/oauth/google}"
set_env "MANOR_GOOGLE_PROFILE_URL" "${MANOR_GOOGLE_PROFILE_URL:-https://app.manorai.xyz/api/v1/auth/me}"

if [ -n "${OPENAI_API_KEY:-}" ]; then
  set_env "OPENAI_API_KEY" "$OPENAI_API_KEY"
fi
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  set_env "OPENROUTER_API_KEY" "$OPENROUTER_API_KEY"
fi
if [ -n "${JWT_SECRET:-}" ]; then
  set_env "JWT_SECRET" "$JWT_SECRET"
fi
if [ -n "${MEETING_NOTE_TAKER_API_KEY:-}" ]; then
  set_env "MEETING_NOTE_TAKER_API_KEY" "$MEETING_NOTE_TAKER_API_KEY"
fi
if [ -n "${VITE_GOOGLE_CLIENT_ID:-}" ]; then
  set_env "VITE_GOOGLE_CLIENT_ID" "$VITE_GOOGLE_CLIENT_ID"
fi

# Operator-seeded overrides are applied last and win over everything above,
# including CI secrets: a key seeded or rotated on the server (e.g. via a
# workflow-dispatch deploy) must survive later push deploys that still carry
# the old secret value in GitHub.
OVERRIDES_FILE="${ENV_OVERRIDES_FILE:-.env.overrides}"
if [ -f "$OVERRIDES_FILE" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|'#'*) continue ;;
      *=*) ;;
      *) continue ;;
    esac
    key="${line%%=*}"
    case "$key" in
      *[!A-Za-z0-9_]*|'') echo "Skipping invalid override key in $OVERRIDES_FILE" >&2; continue ;;
    esac
    set_env "$key" "${line#*=}"
  done < "$OVERRIDES_FILE"
  echo "Applied overrides from $OVERRIDES_FILE"
fi

echo "Rendered $OUTPUT_FILE from $EXAMPLE_FILE"
