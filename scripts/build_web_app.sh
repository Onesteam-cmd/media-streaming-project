#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../mobile"

echo "== TypeScript check =="
npx tsc --noEmit

echo
echo "== Export Expo web build =="
npx expo export --platform web

echo
echo "== Restart web nginx =="
cd ..
docker compose up -d --force-recreate web_nginx

echo
echo "OK: web app rebuilt."
echo "Local:     http://localhost:8091"
if [ -n "${TAILSCALE_IP:-}" ]; then
  echo "Tailscale: http://${TAILSCALE_IP}:8091"
fi
