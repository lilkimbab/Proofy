#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/apps/web"
WEB_HOST="${WEB_HOST:-localhost}"
WEB_PORT="${WEB_PORT:-3000}"

if ! command -v npm >/dev/null 2>&1; then
  echo "[web] npm 이 없습니다. Node.js 와 npm 을 먼저 설치하세요."
  exit 1
fi

if [ ! -f "$WEB_DIR/.env.local" ] && [ -f "$WEB_DIR/.env.local.example" ]; then
  cp "$WEB_DIR/.env.local.example" "$WEB_DIR/.env.local"
fi

cd "$WEB_DIR"
rm -rf "$WEB_DIR/.next"
npm run build
exec node_modules/.bin/next start --hostname "$WEB_HOST" --port "$WEB_PORT"
