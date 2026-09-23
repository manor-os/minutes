#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INDEX_FILE="$ROOT_DIR/phone-recorder/index.html"
APP_FILE="$ROOT_DIR/phone-recorder/src/App.jsx"

assert_contains() {
  local file="$1"
  local needle="$2"
  if ! grep -Fq "$needle" "$file"; then
    echo "Expected $file to contain: $needle" >&2
    exit 1
  fi
}

assert_index_contains() {
  local needle="$1"
  assert_contains "$INDEX_FILE" "$needle"
}

assert_index_contains 'id="google-callback-bootstrap"'
assert_index_contains 'window.location.pathname !== "/googleCallback"'
assert_index_contains 'apiBase + "/api/auth/google-login"'
assert_index_contains 'localStorage.setItem("auth_token", result.token)'
assert_index_contains 'window.location.replace("/")'
assert_contains "$APP_FILE" 'window.__GOOGLE_CALLBACK_BOOTSTRAPPED__'

echo "Google callback bootstrap assertions passed"
