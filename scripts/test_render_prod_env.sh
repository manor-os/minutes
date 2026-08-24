#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cp "$ROOT_DIR/.env.example" "$TMP_DIR/.env.example"

(
  cd "$TMP_DIR"
  MANOR_OAUTH_CLIENT_SECRET="secret-from-ci" \
  OPENAI_API_KEY="openai-from-ci" \
  OPENROUTER_API_KEY="openrouter-from-ci" \
  JWT_SECRET="jwt-from-ci" \
  VITE_GOOGLE_CLIENT_ID="google-client-from-ci" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
)

ENV_FILE="$TMP_DIR/.env"

assert_line() {
  local expected="$1"
  if ! grep -Fxq "$expected" "$ENV_FILE"; then
    echo "Expected line not found: $expected"
    echo "--- .env ---"
    cat "$ENV_FILE"
    exit 1
  fi
}

assert_line "EDITION=cloud"
assert_line "PRODUCTION=true"
assert_line "VITE_API_URL=https://minutes.manorai.xyz"
assert_line "CORS_ORIGINS=https://minutes.manorai.xyz"
assert_line "MANOR_OAUTH_CLIENT_SECRET=secret-from-ci"
assert_line "MANOR_OAUTH_AUTHORIZE_URL=https://app.manorai.xyz/oauth/authorize"
assert_line "MANOR_OAUTH_TOKEN_URL=https://app.manorai.xyz/api/v1/oauth/token"
assert_line "OPENAI_API_KEY=openai-from-ci"
assert_line "OPENROUTER_API_KEY=openrouter-from-ci"
assert_line "JWT_SECRET=jwt-from-ci"
assert_line "VITE_GOOGLE_CLIENT_ID=google-client-from-ci"
assert_line "MANOR_GOOGLE_OAUTH_URL=https://app.manorai.xyz/api/v1/auth/oauth/google"
assert_line "MANOR_GOOGLE_PROFILE_URL=https://app.manorai.xyz/api/v1/auth/me"

# Overrides file wins over CI-provided secrets and persists across renders.
(
  cd "$TMP_DIR"
  printf 'MEETING_NOTE_TAKER_API_KEY=key-from-overrides\n# comment\n\nBAD KEY=x\n' > .env.overrides
  MANOR_OAUTH_CLIENT_SECRET="secret-from-ci" \
  JWT_SECRET="jwt-from-ci" \
  MEETING_NOTE_TAKER_API_KEY="key-from-ci-secret" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
)
assert_line "MEETING_NOTE_TAKER_API_KEY=key-from-overrides"
if grep -Fq "BAD KEY" "$ENV_FILE"; then
  echo "Invalid override key leaked into .env"
  exit 1
fi
rm -f "$TMP_DIR/.env.overrides"

for required_key in \
  MANOR_OAUTH_CLIENT_SECRET \
  JWT_SECRET
do
  if (
    cd "$TMP_DIR"
    MANOR_OAUTH_CLIENT_SECRET="secret-from-ci" \
    OPENAI_API_KEY="openai-from-ci" \
    OPENROUTER_API_KEY="openrouter-from-ci" \
    JWT_SECRET="jwt-from-ci" \
    env "$required_key=" "$ROOT_DIR/scripts/render-prod-env.sh"
  ) >/tmp/render-prod-env-missing-secret.log 2>&1; then
    echo "Expected render-prod-env.sh to fail when $required_key is empty"
    exit 1
  fi
done

BASE_ENV="$TMP_DIR/base.env"
cat > "$BASE_ENV" <<'EOF'
OPENAI_API_KEY=existing-openai
OPENROUTER_API_KEY=existing-openrouter
JWT_SECRET=existing-jwt
MANOR_OAUTH_CLIENT_SECRET=old-secret
EOF

(
  cd "$TMP_DIR"
  ENV_BASE_FILE="$BASE_ENV" \
  MANOR_OAUTH_CLIENT_SECRET="new-secret" \
  JWT_SECRET="existing-jwt" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
)

assert_line "MANOR_OAUTH_CLIENT_SECRET=new-secret"
assert_line "OPENAI_API_KEY=existing-openai"
assert_line "OPENROUTER_API_KEY=existing-openrouter"
assert_line "JWT_SECRET=existing-jwt"
