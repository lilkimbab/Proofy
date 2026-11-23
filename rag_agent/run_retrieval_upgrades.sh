#!/usr/bin/env bash
# Retrieval module upgrades runner.
# 4단계 retrieval 개선 (Hybrid Search → Reranker → Adaptive Chunking → Personalization) 을
# claude -p 로 순차 실행한다. 각 단계의 종료 코드가 0 이 아닐 경우 즉시 중단한다.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

LOG_DIR="${ROOT}/.run_logs"
mkdir -p "$LOG_DIR"

STEPS=(
  "step12_hybrid_search"
  "step13_reranker"
  "step14_adaptive_chunking"
  "step15_personalization"
)

if ! command -v claude >/dev/null 2>&1; then
  echo "[ERROR] 'claude' CLI 가 PATH 에 없습니다. https://docs.claude.com/claude-code 참고" >&2
  exit 1
fi

for step in "${STEPS[@]}"; do
  prompt_path="${ROOT}/prompts/${step}.txt"
  if [[ ! -f "$prompt_path" ]]; then
    echo "[ERROR] 프롬프트 파일 없음: $prompt_path" >&2
    exit 1
  fi

  log_path="${LOG_DIR}/${step}.log"
  echo
  echo "=============================================================="
  echo "▶ ${step}  →  log: ${log_path}"
  echo "=============================================================="

  # claude -p 는 stdin 을 사용하지 않으므로 --print 모드로 프롬프트를 인자로 전달
  if claude -p "$(cat "$prompt_path")" --permission-mode bypassPermissions 2>&1 | tee "$log_path"; then
    echo "[OK] ${step} 완료"
  else
    echo "[FAIL] ${step} 실패. ${log_path} 확인" >&2
    exit 1
  fi
done

echo
echo "=============================================================="
echo "  ALL RETRIEVAL UPGRADES COMPLETE"
echo "  로그: ${LOG_DIR}"
echo "=============================================================="
