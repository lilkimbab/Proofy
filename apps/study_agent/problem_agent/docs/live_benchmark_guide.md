# Live Benchmark Execution Guide

This guide explains how to run a practical live benchmark for `problem_agent`.
Unit tests verify local behavior and contracts. The live benchmark checks whether the current implementation performs well on real lecture materials.

## Purpose

The live benchmark measures:

- retrieval quality from the connected `rag_agent`
- generated problem quality across subjects and problem styles
- total generation latency
- search latency
- LLM generation latency
- quality validation latency
- DB write, commit, and refresh time
- generated artifact publish time
- reject/retry ratio
- repeated-run stability, including quality variance and duplicate reasoning-template risk

Use this after normal unit tests pass. A green unit test run does not prove real lecture retrieval or generated exam-quality problems are good.

## Required Setup

Before running live eval:

1. Start `rag_agent`.
2. Upload and index lecture materials in `rag_agent`.
3. Copy the exact RAG title/document id used during upload.
4. Export `OPENAI_API_KEY`.
5. Optionally export generated artifact URLs if you want to measure publishing latency.

Expected environment:

```bash
export RAG_AGENT_URL=http://localhost:8001
export OPENAI_API_KEY=...
```

Optional artifact publishing:

```bash
export GENERATED_ARTIFACT_INDEX_URL=http://localhost:8001/generated-artifacts/index
export GENERATED_ARTIFACT_ADD_URL=http://localhost:8001/add
export GENERATED_ARTIFACT_PUBLISH_ENABLED=true
```

The benchmark writes to an isolated SQLite DB under the output directory by default. Do not opt into `DATABASE_URL` unless it points to a disposable benchmark DB.

## Prepare Cases

Create a real case file, for example:

```text
evals/live_materials/my_real_cases.jsonl
```

Each line is one JSON object. Important fields:

- `document_id`: exact RAG title/document id from the upload. This must match `rag_agent`.
- `concepts`: user-facing concepts for the request. Keep them close to lecture terminology.
- `expected_search_terms`: terms that should appear in retrieved chunks. Use terms present in the lecture material.
- `expected_problem_terms`: terms that should appear in generated problems, such as `조건`, `판단`, `계산`, `근거`, `trace`, or `comparison`.
- `expected_chunk_ids`: optional golden chunk ids from inspected RAG `/search` results. If provided, Hit@K should be `1.0`.
- `expected_pages`: optional expected source pages.
- `expected_source_spans`: optional short source text spans that should appear in retrieved chunks.
- `thresholds`: per-case gates such as `min_returned_chunks`, `min_average_quality_score`, `max_reject_rate`, and `max_total_ms`.

Practical workflow:

1. Upload a lecture file to `rag_agent`.
2. Run RAG `/search` manually with the planned concepts.
3. Copy useful chunk ids/pages/spans into the case file.
4. Start with `count: 1` or `count: 2` to keep latency and cost manageable.
5. Add both `multiple_choice` and `short_answer` cases.
6. Include both standard and high-rigor cases.

## Recommended First Real Cases

Start with at least 10 cases:

| domain | count | recommended style |
| --- | ---: | --- |
| CS operating systems | 2 | deadlock/resource scheduling, error detection or condition judgment |
| algorithms/data structures | 2 | trace-and-explain, complexity reasoning, exam application |
| math/calculus | 1 | calculation practice with interpretation |
| statistics | 1 | evidence/data interpretation |
| economics | 1 | equilibrium shift or policy scenario application |
| biology | 1 | evidence analysis with condition change |
| law/social science | 1 | concept boundary or case judgment |
| easy/medium control | 1 | concept check to verify baseline generation and latency |

Use real uploaded materials, but keep the case file free of large private lecture excerpts. Short source spans for retrieval verification are enough.

For the current attached data pack, use:

- `evals/live_materials/current_data_material_manifest.json`
- `evals/live_materials/current_data_smoke_cases.jsonl`
- `evals/live_materials/current_data_cases.jsonl`
- `evals/live_materials/CURRENT_DATA_UPLOAD_CHECKLIST.md`

These files are templates until the PDFs are uploaded to `rag_agent` with the listed document IDs and golden chunk labels are reviewed.

## Commands

Normal unit tests:

```bash
./scripts/run_tests.sh
```

Live eval:

```bash
export PROBLEM_AGENT_LIVE_EVAL_ENABLED=true
export PROBLEM_AGENT_LIVE_EVAL_CASES=evals/live_materials/my_real_cases.jsonl
export PROBLEM_AGENT_LIVE_EVAL_OUTPUT_DIR=evals/reports
export PROBLEM_AGENT_LIVE_EVAL_COMPARE_BASELINE_SEARCH=true
export PROBLEM_AGENT_LIVE_EVAL_SEARCH_QUERY_MODE_SWEEP=true
export PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT=3
export PROBLEM_AGENT_LIVE_EVAL_HUMAN_REVIEW_EXPORT_MODE=redacted
export PROBLEM_AGENT_LIVE_EVAL_COST_PROFILE=balanced
export RAG_AGENT_URL=http://localhost:8001
export OPENAI_API_KEY=...
./scripts/run_live_eval.sh
```

Cost profiles:

- `cheap`: low-cost debugging. Uses `PROBLEM_MODEL`, one high-rigor candidate, no high-rigor retry, and disables live-eval LLM judge.
- `balanced`: normal beta smoke validation. Starts on `PROBLEM_MODEL`, uses two high-rigor MCQ candidates, and escalates only when `PROBLEM_AGENT_ALLOW_PREMIUM_ESCALATION=true` and the first attempt fails for evidence/schema/cognitive-demand reasons.
- `full`: release-candidate validation. Preserves premium high-rigor routing and configured retry counts; use this only when token budget is acceptable.

`./scripts/run_live_eval.sh` defaults `PROBLEM_AGENT_LIVE_EVAL_COST_PROFILE=cheap` unless you set it explicitly.

`PROBLEM_AGENT_LIVE_EVAL_SEARCH_QUERY_MODE_SWEEP=true` runs extra retrieval-only comparisons for
`baseline`, `compact`, `hybrid`, and `expanded` query modes. It does not generate problems for every
mode; generation still uses the configured primary `PROBLEM_AGENT_SEARCH_QUERY_MODE`.

`PROBLEM_AGENT_LIVE_EVAL_HUMAN_REVIEW_EXPORT_MODE` controls the human-review CSV:

- `full` keeps answer, explanation, rubric, and source evidence snapshot columns intact for expert review.
- `redacted` keeps question, choices, and source chunk IDs visible, but writes `[redacted]` for answer, explanation, rubric, and source evidence snapshot columns.

Use `redacted` when the CSV might leave the core development/review group.

Current data smoke example after upload and golden review:

```bash
export PROBLEM_AGENT_LIVE_EVAL_ENABLED=true
export PROBLEM_AGENT_LIVE_EVAL_CASES=evals/live_materials/current_data_smoke_cases.jsonl
export PROBLEM_AGENT_LIVE_EVAL_OUTPUT_DIR=evals/reports/current_data_smoke
export PROBLEM_AGENT_LIVE_EVAL_COMPARE_BASELINE_SEARCH=true
export PROBLEM_AGENT_LIVE_EVAL_SEARCH_QUERY_MODE_SWEEP=true
export PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT=2
export PROBLEM_AGENT_LIVE_EVAL_HUMAN_REVIEW_EXPORT_MODE=redacted
export PROBLEM_AGENT_LIVE_EVAL_ANSWER_VERIFICATION_ENABLED=true
./scripts/run_live_eval.sh
```

Commercial readiness should use at least 30 logical cases with repeat count `3`, followed by human review of generated problems and source grounding.

Optional LLM judge:

```bash
export PROBLEM_AGENT_LIVE_EVAL_LLM_JUDGE_ENABLED=true
export PROBLEM_AGENT_LIVE_EVAL_JUDGE_MODEL=gpt-5.5
./scripts/run_live_eval.sh
```

Output files:

- `evals/reports/live_problem_generation_report.json`
- `evals/reports/live_problem_generation_cases.jsonl`
- `evals/reports/live_problem_generation_summary.md`
- `evals/reports/live_problem_generation_human_review.csv`
- `evals/reports/live_problem_generation_human_review_summary.json` after summarizing reviewer-filled CSV
- `evals/reports/live_problem_generation_human_review_summary.md` after summarizing reviewer-filled CSV
- `evals/reports/live_problem_generation_eval.sqlite`

Before interpreting an existing JSON report, check its freshness metadata:

- `report_schema_version` should be `live_problem_generation_eval.v2`.
- `cases_sha256` should match the current cases file.
- `generated_at` should be newer than the cases file modified time.
- `case_count` should be greater than zero.

If any of these checks fail, ignore the old report and rerun the live benchmark. The report also includes `git_commit` and a safe `settings_snapshot` so benchmark results can be tied back to the code and non-secret runtime settings that produced them.

## Interpret Results

Initial threshold suggestions:

| metric | suggested gate |
| --- | ---: |
| standard `reject_rate` | `<= 0.35` |
| high-rigor `reject_rate` | `<= 0.60` |
| average `actual_retry_count` | `<= 0.8` |
| high-rigor average quality | `>= 0.75` |
| `expected_search_term_coverage` | `>= 0.40` |
| `expected_problem_term_coverage` | `>= 0.30` |
| Hit@K when `expected_chunk_ids` exist | `1.0` |
| high-rigor repeat pass rate | `>= 0.67` |
| repeated question similarity | `<= 0.85` |
| `count` 1-2 `total_ms` target | `<= 45000` |
| `count` 3-5 `total_ms` target | `<= 80000` |

Read these report sections first:

- Case summary: broad pass/fail and latency.
- Lowest search-quality cases: retrieval failures.
- Lowest problem-quality cases: weak generated items.
- High-rigor operation distribution: whether hard problems use specific thinking operations.
- Repeated-run stability: whether repeated generations keep passing without collapsing into duplicate question templates.
- Bottleneck distribution: dominant latency source.
- Human review CSV: manual review of private answer/explanation/rubric fields.
- LLM judge section: optional external judge score, recommended action, and independence warnings.
  If the judge model is the same as the generation model, treat the judge score as weak evidence.
  If both models are from the same family, such as GPT or Gemini, use human review for release decisions.

## What To Do When Failing

Search quality is low:

- Confirm `document_id` exactly matches the RAG upload title/id.
- Check whether expected terms actually exist in the material.
- Inspect RAG indexing and `/search` output.
- Compare baseline vs enhanced query results.
- Use search query mode sweep to see whether `compact`, `hybrid`, or `expanded` gives the best retrieval score.
- Adjust query expansion only in `problem_agent`; do not edit `rag_agent`.

Problem quality is low:

- Inspect high-rigor operation distribution.
- Look for `definition_recall` or `generic_application` dominating hard cases.
- Check missing diagnostics for multiple-choice problems.
- Check missing rubric for short-answer problems.
- Review `live_problem_generation_human_review.csv`.
- Use `PROBLEM_AGENT_LIVE_EVAL_HUMAN_REVIEW_EXPORT_MODE=redacted` before sharing the CSV outside expert reviewers.
- Import reviewer-filled CSV with `load_human_review_csv`, summarize with `summarize_human_review`, and write summary files with `write_human_review_summary`.

Human review calibration targets:

- average human problem quality `>= 0.75`
- average source grounding `>= 0.80`
- no answer correctness errors in reviewer notes
- professor-vs-human disagreements must be manually reviewed before trusting heuristic scores

Reject/retry ratio is high:

- Inspect rejection categories and retry feedback in `quality_summary.performance`.
- Check whether cases demand unsupported problem styles for the retrieved chunks.
- Improve prompts or candidate planning without lowering quality thresholds.

Repeated-run stability is weak:

- Check `case_stability_summary` in the JSON report.
- If repeat pass rate is low, inspect repeated rejection categories before changing thresholds.
- If question similarity is high, improve prompt diversity or duplicate reasoning-template detection.
- If the same high-rigor operation appears every repeat, add or tune thinking-operation templates for that problem style.

Latency is high:

- Inspect latency percentiles and bottleneck distribution.
- If search dominates, check RAG latency and returned payload size.
- If generation dominates, reduce `count` or candidate expansion for exploratory runs.
- If quality filtering dominates, inspect reject/retry loops.
- If DB dominates, check local SQLite or configured database performance.

Artifact publishing is slow:

- Check `artifact_publish_ms`.
- Check generated artifact server latency.
- Confirm publish concurrency and timeout settings.
- Disable publishing for pure generation-quality experiments.

## Archetype Kernel Smoke

Use `evals/live_materials/archetype_cases.jsonl` to validate the domain-general kernel layer by content structure and reasoning operation rather than by subject family. Start with one repeat and no query sweep:

```bash
export PROBLEM_AGENT_LIVE_EVAL_ENABLED=true
export PROBLEM_AGENT_LIVE_EVAL_CASES=evals/live_materials/archetype_cases.jsonl
export PROBLEM_AGENT_LIVE_EVAL_OUTPUT_DIR=evals/reports/archetype_smoke
export PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT=1
export PROBLEM_AGENT_LIVE_EVAL_SEARCH_QUERY_MODE_SWEEP=false
export PROBLEM_AGENT_LIVE_EVAL_ANSWER_VERIFICATION_ENABLED=true
./scripts/run_live_eval.sh
```

This is still a smoke benchmark. Do not treat product quality as verified until the archetype run passes and the human-review CSV has been reviewed.

## Ownership Rule

`problem_agent` only consumes the RAG contract. It may inspect RAG responses and adapt its search query, but it must not modify `rag_agent`.
