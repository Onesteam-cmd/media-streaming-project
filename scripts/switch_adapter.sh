#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: ./scripts/switch_adapter.sh <adapter_name>"
  echo "Example: ./scripts/switch_adapter.sh local_demo"
  echo "Example: ./scripts/switch_adapter.sh internet_archive"
  echo "Example: ./scripts/switch_adapter.sh torrent_demo"
  exit 1
fi

ADAPTER="$1"

case "$ADAPTER" in
  local_demo|internet_archive|torrent_demo|supervised_external)
    ;;
  *)
    echo "ERROR: unknown adapter: $ADAPTER"
    echo "Allowed: local_demo, internet_archive, torrent_demo, supervised_external"
    exit 1
    ;;
esac

python3 - "$ADAPTER" <<'PY'
import sys
from pathlib import Path

adapter = sys.argv[1]
path = Path(".env")

lines = path.read_text(encoding="utf-8").splitlines()

new_lines = []
found = False

for line in lines:
    if line.startswith("INGEST_ADAPTER="):
        new_lines.append(f"INGEST_ADAPTER={adapter}")
        found = True
    else:
        new_lines.append(line)

if not found:
    new_lines.append(f"INGEST_ADAPTER={adapter}")

path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
PY

docker compose up -d --force-recreate backend

sleep 2

curl -s http://localhost:8000/health | python3 -m json.tool
