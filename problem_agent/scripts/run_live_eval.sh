#!/usr/bin/env bash
set -euo pipefail

detect_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if [[ ! -x "$PYTHON_BIN" ]] && ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      echo "PYTHON_BIN is set but not executable or not found: $PYTHON_BIN" >&2
      exit 1
    fi
    printf '%s\n' "$PYTHON_BIN"
    return
  fi

  if [[ -x "./.venv/bin/python" ]]; then
    printf '%s\n' "./.venv/bin/python"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi

  echo "No Python interpreter found. Set PYTHON_BIN or create ./.venv/bin/python." >&2
  exit 1
}

require_env() {
  local missing=()
  for name in \
    PROBLEM_AGENT_LIVE_EVAL_ENABLED \
    RAG_AGENT_URL \
    OPENAI_API_KEY \
    PROBLEM_AGENT_LIVE_EVAL_CASES
  do
    if [[ -z "${!name:-}" ]]; then
      missing+=("$name")
    fi
  done

  if [[ "${PROBLEM_AGENT_LIVE_EVAL_ENABLED:-}" != "true" ]]; then
    missing+=("PROBLEM_AGENT_LIVE_EVAL_ENABLED must be true")
  fi

  if (( ${#missing[@]} > 0 )); then
    echo "Missing required live eval environment:" >&2
    for name in "${missing[@]}"; do
      echo "- $name" >&2
    done
    exit 1
  fi
}

PY="$(detect_python)"
echo "Using Python: $PY"
"$PY" --version
require_env

export PROBLEM_AGENT_LIVE_EVAL_COST_PROFILE="${PROBLEM_AGENT_LIVE_EVAL_COST_PROFILE:-cheap}"

"$PY" -m pytest tests/test_live_problem_generation_benchmark.py -m "llm and rag" -q
