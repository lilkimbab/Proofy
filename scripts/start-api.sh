#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
API_VENV="$API_DIR/.venv"

if [ ! -d "$API_VENV" ]; then
  echo "[api] .venv 가 없습니다. 먼저 ./scripts/bootstrap.sh 를 실행하세요."
  exit 1
fi

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

export APP_ALLOWED_ORIGINS="${APP_ALLOWED_ORIGINS:-http://localhost:3000,http://localhost:3003}"
export APP_STORAGE_BACKEND="${APP_STORAGE_BACKEND:-memory}"

cd "$API_DIR"
# shellcheck disable=SC1091
source "$API_VENV/bin/activate"
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
