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

for required_key in MANOR_OAUTH_CLIENT_SECRET; do
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

# A first deployment still needs an explicit JWT secret.
FIRST_DEPLOY_ENV="$TMP_DIR/first-deploy.env"
if (
  cd "$TMP_DIR"
  ENV_OUTPUT_FILE="$FIRST_DEPLOY_ENV" \
  ENV_BASE_FILE="$FIRST_DEPLOY_ENV" \
  MANOR_OAUTH_CLIENT_SECRET="secret-from-ci" \
  JWT_SECRET="" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
) >/tmp/render-prod-env-missing-secret.log 2>&1; then
  echo "Expected a first deployment without JWT_SECRET to fail"
  exit 1
fi

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
  JWT_SECRET="new-jwt" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
)

assert_line "MANOR_OAUTH_CLIENT_SECRET=new-secret"
assert_line "OPENAI_API_KEY=existing-openai"
assert_line "OPENROUTER_API_KEY=existing-openrouter"
assert_line "JWT_SECRET=new-jwt"

# Existing production installs keep their signing key when the CI secret is
# absent, so a routine deploy does not invalidate active sessions.
PRESERVED_ENV="$TMP_DIR/preserved.env"
(
  cd "$TMP_DIR"
  ENV_BASE_FILE="$BASE_ENV" \
  ENV_OUTPUT_FILE="$PRESERVED_ENV" \
  MANOR_OAUTH_CLIENT_SECRET="new-secret" \
  JWT_SECRET="" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
)
grep -Fxq "JWT_SECRET=existing-jwt" "$PRESERVED_ENV" || {
  echo "Existing JWT_SECRET was not preserved"
  exit 1
}

JWT_OVERRIDE_FILE="$TMP_DIR/jwt-overrides.env"
JWT_OVERRIDE_ENV="$TMP_DIR/jwt-override-output.env"
printf 'JWT_SECRET=operator-jwt\n' > "$JWT_OVERRIDE_FILE"
(
  cd "$TMP_DIR"
  ENV_BASE_FILE="$BASE_ENV" \
  ENV_OUTPUT_FILE="$JWT_OVERRIDE_ENV" \
  ENV_OVERRIDES_FILE="$JWT_OVERRIDE_FILE" \
  MANOR_OAUTH_CLIENT_SECRET="new-secret" \
  JWT_SECRET="" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
)
grep -Fxq "JWT_SECRET=operator-jwt" "$JWT_OVERRIDE_ENV" || {
  echo "Operator JWT_SECRET override did not win"
  exit 1
}

# Reject an empty override without altering the existing production file.
REJECTED_ENV="$TMP_DIR/rejected-empty-jwt.env"
cp "$PRESERVED_ENV" "$REJECTED_ENV"
printf 'JWT_SECRET=\n' > "$JWT_OVERRIDE_FILE"
if (
  cd "$TMP_DIR"
  ENV_OUTPUT_FILE="$REJECTED_ENV" \
  ENV_OVERRIDES_FILE="$JWT_OVERRIDE_FILE" \
  MANOR_OAUTH_CLIENT_SECRET="new-secret" \
  JWT_SECRET="" \
  "$ROOT_DIR/scripts/render-prod-env.sh"
) >/tmp/render-prod-env-empty-override.log 2>&1; then
  echo "Expected an empty JWT_SECRET override to fail"
  exit 1
fi
cmp -s "$PRESERVED_ENV" "$REJECTED_ENV" || {
  echo "Rejected JWT_SECRET override altered the existing production file"
  exit 1
}
