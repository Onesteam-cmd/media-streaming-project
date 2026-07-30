#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
CANDIDATE_ID="local-demo-big-buck-bunny"
TEST_FILE="media/movies/big_buck_bunny.mp4"

echo "== Smoke test: backend health =="
curl -s "$BASE_URL/health" | python3 -m json.tool

echo
echo "== Smoke test: system status =="
curl -s "$BASE_URL/api/system/status" | python3 -m json.tool

echo
echo "== Smoke test: adapters =="
curl -s "$BASE_URL/api/adapters" | python3 -m json.tool

echo
echo "== Smoke test: Jellyfin status =="
curl -s "$BASE_URL/api/jellyfin/status" | python3 -m json.tool

echo
echo "== Smoke test: Jellyfin libraries =="
curl -s "$BASE_URL/api/jellyfin/libraries" | python3 -m json.tool

echo
echo "== Smoke test: search local catalog =="
SEARCH_COUNT=$(curl -s -X POST "$BASE_URL/api/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"bunny"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])")

if [ "$SEARCH_COUNT" != "1" ]; then
  echo "ERROR: expected search count 1, got $SEARCH_COUNT"
  exit 1
fi

echo "OK: search returned 1 candidate"

echo
echo "== Smoke test: failed request when file is missing =="
rm -f "$TEST_FILE"

FAILED_REQUEST_ID=$(curl -s -X POST "$BASE_URL/api/requests" \
  -H "Content-Type: application/json" \
  -d "{\"candidate_id\":\"$CANDIDATE_ID\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['request']['id'])")

sleep 1

FAILED_STATUS=$(curl -s "$BASE_URL/api/requests/$FAILED_REQUEST_ID" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['request']['status'])")

if [ "$FAILED_STATUS" != "failed" ]; then
  echo "ERROR: expected failed status, got $FAILED_STATUS"
  exit 1
fi

echo "OK: missing file request failed as expected"

echo
echo "== Smoke test: completed request when file exists =="
echo "temporary backend test file" > "$TEST_FILE"

COMPLETED_REQUEST_ID=$(curl -s -X POST "$BASE_URL/api/requests" \
  -H "Content-Type: application/json" \
  -d "{\"candidate_id\":\"$CANDIDATE_ID\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['request']['id'])")

sleep 1

COMPLETED_STATUS=$(curl -s "$BASE_URL/api/requests/$COMPLETED_REQUEST_ID" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['request']['status'])")

rm -f "$TEST_FILE"

if [ "$COMPLETED_STATUS" != "completed" ]; then
  echo "ERROR: expected completed status, got $COMPLETED_STATUS"
  exit 1
fi

echo "OK: existing file request completed as expected"

echo
echo "== Smoke test: Jellyfin scan =="
curl -s -X POST "$BASE_URL/api/jellyfin/scan" | python3 -m json.tool

echo
echo "SMOKE TEST PASSED"
