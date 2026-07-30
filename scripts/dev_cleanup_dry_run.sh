#!/usr/bin/env bash
set -euo pipefail

echo "== Dev cleanup dry-run =="
echo "Этот скрипт ничего не удаляет. Он только показывает runtime-данные."

echo
echo "== SQLite database =="
if [ -f backend/data/app.db ]; then
  ls -lah backend/data/app.db
else
  echo "backend/data/app.db не найден"
fi

echo
echo "== Media files =="
find media/movies -maxdepth 1 -type f ! -name ".gitkeep" -print -exec ls -lh {} \;

echo
echo "== Transmission downloads =="
find transmission/downloads -type f ! -name ".gitkeep" -print -exec ls -lh {} \;

echo
echo "== Transmission torrents from API =="
curl -s http://localhost:8000/api/transmission/torrents | python3 -m json.tool

echo
echo "DRY RUN COMPLETE"
