#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_pid_file() {
  local name="$1"
  local pid_file="$2"
  if [ ! -f "$pid_file" ]; then
    echo "[$name] pid 파일이 없습니다."
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    echo "[$name] pid 파일이 비어 있습니다."
    rm -f "$pid_file"
    return 0
  fi
  if kill -0 "$pid" >/dev/null 2>&1; then
    pkill -P "$pid" >/dev/null 2>&1 || true
    kill "$pid"
    echo "[$name] 종료: $pid"
  else
    echo "[$name] 이미 종료됨: $pid"
  fi
  rm -f "$pid_file"
}

stop_pid_file "api" "$RUN_DIR/api.pid"
stop_pid_file "web" "$RUN_DIR/web.pid"

pkill -f "next dev --webpack" >/dev/null 2>&1 || true
pkill -f "next start --hostname localhost --port 3000" >/dev/null 2>&1 || true
pkill -f "next start --hostname localhost --port 3003" >/dev/null 2>&1 || true
