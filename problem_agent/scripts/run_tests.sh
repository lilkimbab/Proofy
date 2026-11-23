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

PY="$(detect_python)"
echo "Using Python: $PY"
"$PY" --version

"$PY" -m compileall app tests

OPENAI_API_KEY= \
GEMINI_API_KEY= \
RAG_AGENT_URL= \
SEARCH_AGENT_URL= \
GENERATED_ARTIFACT_INDEX_URL= \
GENERATED_ARTIFACT_ADD_URL= \
GENERATED_ARTIFACT_PUBLISH_ENABLED=false \
LLM_FALLBACK_ENABLED=true \
"$PY" -m pytest -m "not llm and not rag" -q
