#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
WEB_DIR="$ROOT_DIR/apps/web"
API_VENV="$API_DIR/.venv"

echo "[bootstrap] root: $ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[bootstrap] python3 가 필요합니다."
  exit 1
fi

if [ ! -d "$API_VENV" ]; then
  echo "[bootstrap] api 가상환경 생성"
  python3 -m venv "$API_VENV"
fi

echo "[bootstrap] api 의존성 설치"
# shellcheck disable=SC1091
source "$API_VENV/bin/activate"
pip install -r "$API_DIR/requirements.txt"
deactivate

if [ ! -f "$ROOT_DIR/.env" ] && [ -f "$ROOT_DIR/.env.example" ]; then
  echo "[bootstrap] 루트 .env 생성"
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
fi

if [ ! -f "$WEB_DIR/.env.local" ] && [ -f "$WEB_DIR/.env.local.example" ]; then
  echo "[bootstrap] web .env.local 생성"
  cp "$WEB_DIR/.env.local.example" "$WEB_DIR/.env.local"
fi

if command -v npm >/dev/null 2>&1; then
  echo "[bootstrap] web 의존성 설치"
  (
    cd "$WEB_DIR"
    npm install
  )
else
  echo "[bootstrap] npm 이 없어 web 의존성 설치는 건너뜁니다."
fi

echo "[bootstrap] 완료"
