# Testing

Use the scripts in `scripts/` so validation does not depend on whether the
machine exposes `python`, `python3`, or `./.venv/bin/python`.

## Normal Unit Tests

Run from `problem_agent/`:

```bash
./scripts/run_tests.sh
```

The script detects Python in this order:

1. `$PYTHON_BIN`
2. `./.venv/bin/python`
3. `python3`
4. `python`

Normal unit tests intentionally do not use real external service settings. The
script clears OpenAI, Gemini, RAG, Search Agent, and generated-artifact URLs for
the pytest process, enables deterministic fallback, and runs:

```bash
$PY -m compileall app tests
$PY -m pytest -m "not llm and not rag" -q
```

This means a local `.env` may contain real API keys without causing normal unit
tests to call OpenAI, Gemini, RAG, or generated-artifact endpoints.

## Live Evaluation

Live evaluation is explicit and should be run only when the RAG service is
running, an OpenAI key is available, and the eval case file points to uploaded
RAG titles.

Required environment:

```bash
export PROBLEM_AGENT_LIVE_EVAL_ENABLED=true
export RAG_AGENT_URL=http://localhost:8001
export OPENAI_API_KEY=...
export PROBLEM_AGENT_LIVE_EVAL_CASES=evals/live_materials/example_cases.jsonl
export PROBLEM_AGENT_LIVE_EVAL_OUTPUT_DIR=evals/reports
export PROBLEM_AGENT_LIVE_EVAL_COMPARE_BASELINE_SEARCH=true
```

Then run:

```bash
./scripts/run_live_eval.sh
```

The live script checks required variables before running and never prints API
key values.

Before a live run, replace all `REPLACE_WITH_*_DOCUMENT_TITLE` placeholders in
`evals/live_materials/example_cases.jsonl` with the exact title/document id used
when uploading the material to `rag_agent`.
