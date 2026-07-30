#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8091}"
PROFILE_ID="${PROFILE_ID:-default}"

env_value() {
  local key="$1"
  local file=".env"

  if [ ! -f "$file" ]; then
    return 0
  fi

  grep -E "^${key}=" "$file" \
    | tail -n 1 \
    | sed -E "s/^${key}=//" \
    | sed -E 's/^["'\'']//; s/["'\'']$//'
}

json_string() {
  python3 - "$1" <<'EOF_JSON'
import json
import sys

print(json.dumps(sys.argv[1]))
EOF_JSON
}

PROJECT_CHECK_AUTH_TOKEN="${PROJECT_CHECK_AUTH_TOKEN:-}"
PROJECT_CHECK_USERNAME="${PROJECT_CHECK_USERNAME:-}"
PROJECT_CHECK_PASSWORD="${PROJECT_CHECK_PASSWORD:-}"

if [ -z "$PROJECT_CHECK_USERNAME" ]; then
  PROJECT_CHECK_USERNAME="$PROFILE_ID"
fi

AUTH_HEADERS=()

if [ -n "$PROJECT_CHECK_AUTH_TOKEN" ]; then
  AUTH_HEADERS=(-H "Authorization: Bearer ${PROJECT_CHECK_AUTH_TOKEN}")
elif [ -n "$PROJECT_CHECK_PASSWORD" ]; then
  LOGIN_PAYLOAD="$(
    python3 - "$PROJECT_CHECK_USERNAME" "$PROJECT_CHECK_PASSWORD" <<'EOF_JSON'
import json
import sys

print(json.dumps({
    "username": sys.argv[1],
    "password": sys.argv[2],
}))
EOF_JSON
  )"

  LOGIN_RESPONSE="$(curl -s -X POST "$BASE_URL/api/auth/login" -H "Content-Type: application/json" -d "$LOGIN_PAYLOAD")"

  PROJECT_CHECK_AUTH_TOKEN="$(
    python3 - <<'EOF_JSON' "$LOGIN_RESPONSE"
import json
import sys

data = json.loads(sys.argv[1])
print(data.get("token", ""))
EOF_JSON
  )"

  if [ -z "$PROJECT_CHECK_AUTH_TOKEN" ]; then
    echo "ERROR: could not login for project check."
    echo "$LOGIN_RESPONSE" | python3 -m json.tool
    exit 1
  fi

  AUTH_HEADERS=(-H "Authorization: Bearer ${PROJECT_CHECK_AUTH_TOKEN}")
else
  PROFILE_AUTH_ENABLED="${PROFILE_AUTH_ENABLED:-$(env_value PROFILE_AUTH_ENABLED)}"
  PROFILE_PIN="${PROFILE_PIN:-}"

  if [ -z "$PROFILE_PIN" ]; then
    if [ "$PROFILE_ID" = "second" ]; then
      PROFILE_PIN="$(env_value PROFILE_SECOND_PIN)"
    else
      PROFILE_PIN="$(env_value PROFILE_DEFAULT_PIN)"
    fi
  fi

  AUTH_HEADERS=(-H "X-User-Id: ${PROFILE_ID}")

  if [ -n "$PROFILE_PIN" ]; then
    AUTH_HEADERS+=(-H "X-Profile-Pin: ${PROFILE_PIN}")
  fi

  if [ "${PROFILE_AUTH_ENABLED:-false}" = "true" ] && [ -z "$PROFILE_PIN" ]; then
    echo "ERROR: PROFILE_AUTH_ENABLED=true, but no PIN was found for PROFILE_ID=${PROFILE_ID}."
    echo "Set PROFILE_PIN manually or use account auth:"
    echo "  PROJECT_CHECK_PASSWORD=... ./scripts/project_check.sh"
    exit 1
  fi
fi

echo "== Project check: readiness =="
READY=$(curl -s "$BASE_URL/api/readiness" | python3 -c "import sys,json; print(json.load(sys.stdin)['ready'])")

if [ "$READY" != "True" ]; then
  echo "ERROR: readiness is not true"
  curl -s "$BASE_URL/api/readiness" | python3 -m json.tool
  exit 1
fi

echo "OK: readiness true"

echo
echo "== Project check: adapters =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/adapters" | python3 -m json.tool

echo
echo "== Project check: Jellyfin libraries =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/jellyfin/libraries" | python3 -m json.tool

echo
echo "== Project check: Transmission status =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/transmission/status" | python3 -m json.tool

echo
echo "== Project check: Transmission torrents =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/transmission/torrents" | python3 -m json.tool

echo
echo "== Project check: recent candidates =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/candidates?limit=5" | python3 -m json.tool

echo
echo "== Project check: recent requests (${PROFILE_ID}) =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/requests?limit=5" | python3 -m json.tool

echo
echo "== Project check: prepared media (${PROFILE_ID}) =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/media/prepared" | python3 -m json.tool

echo
echo "== Project check: watch positions (${PROFILE_ID}) =="
curl -s "${AUTH_HEADERS[@]}" "$BASE_URL/api/watch-positions" | python3 -m json.tool

echo
echo "PROJECT CHECK PASSED"
