#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../mobile"

TAILSCALE_IP="${TAILSCALE_IP:-}"

if [ -z "$TAILSCALE_IP" ]; then
  echo "ERROR: set TAILSCALE_IP before launch." >&2
  echo "Example: TAILSCALE_IP=100.x.y.z ./scripts/start_mobile_tailscale.sh" >&2
  exit 1
fi

echo "Starting Expo Metro on Tailscale IP: ${TAILSCALE_IP}"
echo "Expected URL: exp://${TAILSCALE_IP}:8081"

REACT_NATIVE_PACKAGER_HOSTNAME="${TAILSCALE_IP}" npx expo start --lan --clear
