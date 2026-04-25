#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
WEB_HOST="${WEB_HOST:-localhost}"
WEB_PORT="${WEB_PORT:-3000}"
mkdir -p "$RUN_DIR"

cleanup_existing_pid() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "[start-all] 이미 실행 중인 프로세스가 있습니다: $pid"
      exit 1
    fi
    rm -f "$pid_file"
  fi
}

cleanup_existing_pid "$RUN_DIR/api.pid"
cleanup_existing_pid "$RUN_DIR/web.pid"

echo "[start-all] api 시작"
nohup "$ROOT_DIR/scripts/start-api.sh" >"$RUN_DIR/api.log" 2>&1 &
echo $! >"$RUN_DIR/api.pid"

echo "[start-all] web 시작"
nohup "$ROOT_DIR/scripts/start-web.sh" >"$RUN_DIR/web.log" 2>&1 &
echo $! >"$RUN_DIR/web.pid"

echo "[start-all] 완료"
echo "  api: http://localhost:8000/docs"
echo "  web: http://$WEB_HOST:$WEB_PORT"
echo "  logs:"
echo "    tail -f $RUN_DIR/api.log"
echo "    tail -f $RUN_DIR/web.log"
