# Live Problem Generation Materials

This directory contains optional JSONL case templates for live multi-material problem generation benchmarks. These cases are not normal unit-test fixtures. They require a running RAG service and an LLM key only when explicitly enabled.

For the full execution workflow, thresholds, and failure triage, see `docs/live_benchmark_guide.md`.

## Before Running

1. Replace each `document_id` placeholder with the exact RAG title/document id used when uploading the material to `rag_agent`.
2. `expected_search_terms` should be terms that must appear in retrieved chunks. Use terms that are actually present in the lecture material.
3. `expected_problem_terms` should be terms that should appear in generated problems. Use terms that reflect the desired task, such as condition, 판단, 계산, 근거, comparison, or trace.
4. Use `expected_search_term_aliases` and `expected_problem_term_aliases` for notation variants such as `B+ tree`, `B+-Tree`, `B[+] -Tree`, `disk I/O`, `disk io`, and `I/O cost`.
5. For stronger retrieval checks, optionally fill `expected_chunk_ids`, `expected_pages`, and `expected_source_spans` after inspecting RAG `/search` results.
6. Keep `count` at `1` or `2` for latency testing. Larger counts make LLM generation and quality filtering slower.
7. Include both `multiple_choice` and `short_answer` cases.
8. Include both standard cases and hard/high-rigor cases. Standard cases check baseline product behavior, while high-rigor cases check exam-like reasoning.
9. Do not paste private lecture content into these JSONL files. Put only short source spans needed for retrieval verification.

## Files

- `example_cases.jsonl`: practical placeholder cases across several lecture domains.
- `case_template.jsonl`: a single copyable skeleton for adding a new material.
- `cse321_indexing_cases.jsonl`: regression cases from the CSE321 indexing live benchmark.
- `current_data_material_manifest.json`: manifest for the current attached PDF pack.
- `current_data_cases.jsonl`: full current-data benchmark suite.
- `current_data_smoke_cases.jsonl`: smaller smoke subset for quick live runs.

## Case Format

Each JSONL line is one benchmark case:

```json
{
  "id": "os_deadlock_hard_mcq",
  "description": "운영체제 교착상태 자료에서 조건 변화형 고난도 객관식 생성",
  "document_id": "REPLACE_WITH_OS_DOCUMENT_TITLE",
  "concepts": ["교착상태", "상호배제", "점유와 대기"],
  "request": {
    "type": "multiple_choice",
    "count": 2,
    "difficulty": "hard",
    "bloom_level": "analyze",
    "goal": "exam_prep",
    "course_level": "university",
    "target_rigor": "high",
    "quality_mode": "strict",
    "problem_style": "error_detection",
    "user_requirements": "조건을 바꿨을 때 교착상태가 성립하는지 판단하는 문제"
  },
  "expected_search_terms": ["교착상태", "상호배제", "점유", "대기"],
  "expected_problem_terms": ["조건", "판단"],
  "expected_search_term_aliases": {},
  "expected_problem_term_aliases": {},
  "expected_chunk_ids": [],
  "expected_pages": [],
  "expected_source_spans": [],
  "irrelevant_terms": [],
  "golden_label_mode": "partial",
  "min_returned_chunks": 2,
  "min_cited_chunks_per_problem": 1,
  "min_average_quality_score": 0.72,
  "min_hit_at_k": null,
  "min_mrr_at_k": null,
  "min_precision_at_k": null,
  "min_cited_expected_chunk_recall": null,
  "min_cited_expected_chunk_precision": null,
  "min_cited_source_span_coverage": null,
  "min_repeat_pass_rate": null,
  "max_repeat_quality_score_stddev": null,
  "max_repeat_duplicate_similarity": null,
  "max_reject_rate": 0.55,
  "max_total_ms": 60000
}
```

Term coverage uses canonical normalization plus aliases. Literal substring matching is still used as a fallback, but normalized matching handles common notation variants:

- `B[+] -Tree`, `B+-Tree`, and `B+ tree`
- `disk I/O`, `disk io`, and `I/O cost`

Alias dictionaries are keyed by the canonical term from `expected_search_terms` or `expected_problem_terms`. A term is counted as matched when the canonical term or any alias appears after normalization.

## Golden Retrieval Labels

The basic search metrics use term coverage, but golden labels are better when you know which evidence should be retrieved.

After uploading a lecture file, call RAG `/search` with the same concepts and inspect the returned chunks. Then fill any of these optional fields:

- `expected_chunk_ids`: exact chunk ids that should be retrieved. If present, live eval computes `hit_at_k`, `mrr_at_k`, and `precision_at_k`; `hit_at_k` defaults to requiring at least one hit.
- `golden_label_mode`: use `"partial"` when `expected_chunk_ids` are representative must-have chunks, not every relevant chunk. Use `"exhaustive"` only when you have labeled all relevant chunks.
- `expected_pages`: page numbers that should appear in retrieved chunks.
- `expected_source_spans`: short text spans that should appear in retrieved chunk content. Keep these short and non-private where possible. If present, source span coverage defaults to at least `0.5`.
- `irrelevant_terms`: terms that should not appear in good retrieval results. These are reported as warning/risk signals, not automatic failures.

You can tighten golden-label gates per case with:

- `min_hit_at_k`
- `min_mrr_at_k`
- `min_precision_at_k` only when `golden_label_mode` is `"exhaustive"`. Do not set this for partial labels unless you have a specific reason.
- `min_cited_expected_chunk_recall`
- `min_cited_expected_chunk_precision`
- `min_cited_source_span_coverage`

The report also shows cited-evidence metrics. These check whether the generated problems cite the expected evidence chunks, not just whether search retrieved them.

When `PROBLEM_AGENT_LIVE_EVAL_COMPARE_BASELINE_SEARCH=true`, the report also includes baseline/enhanced `hit_at_k`, `mrr_at_k`, `precision_at_k`, and `source_span_coverage`.

## Repeated-Run Stability

Set `PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT` to run every logical case multiple times:

```bash
export PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT=3
```

Allowed range is `1` to `10`; default is `1`. Repeats use separate user ids such as `live_eval_<case_id>_r0`, `live_eval_<case_id>_r1`, and so on.

The report keeps one result per repeated run and adds `case_stability_summary` per logical case. It includes repeat pass rate, average reject rate, average retry count, quality score standard deviation, operation counts, max question similarity, and repeated reasoning-template count.

Optional per-case stability gates:

- `min_repeat_pass_rate`: default `0.67` for high-rigor cases.
- `max_repeat_quality_score_stddev`: no default.
- `max_repeat_duplicate_similarity`: default `0.85` when repeat count is greater than `1`.

Use repeat count `2` or `3` for commercial smoke checks. Higher values are useful before releases but increase cost and runtime.

## Current Data Pack Suite

`current_data_cases.jsonl` is a material-specific benchmark suite template for the attached current data pack. It covers biology, statistics, physics, linguistics, NLP, Korean ML sequence modeling, computer vision, economics/game theory, and C++ dynamic memory.

The Korean accounting material is intentionally excluded from this current-data test suite because its size makes local test and benchmark iteration too heavy. Add it back only as a separate targeted suite when needed.

Before live use:

1. Extract or place PDFs under `evals/source_materials/current_data_pack/`.
2. Upload every PDF to `rag_agent` with the exact document IDs in `CURRENT_DATA_UPLOAD_CHECKLIST.md`.
3. Run `scripts/bootstrap_live_case_goldens.py` to suggest partial golden chunk IDs and source spans.
4. Manually review suggestions before applying them.
5. Keep `golden_label_mode="partial"` and do not add `min_precision_at_k` unless all relevant chunks are exhaustively labeled.

For commercial smoke, run at least 30 logical cases with `PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT=3` before making release-quality claims. The current smoke subset is intentionally smaller for faster iteration.

## CSE321 Indexing Regression Suite

`cse321_indexing_cases.jsonl` preserves the observed CSE321 indexing benchmark as a repeatable product-quality regression suite. It assumes the CSE321 indexing PDF has been uploaded to `rag_agent` with this exact RAG title/document id:

```text
cse321_indexing_live
```

To recreate the suite:

1. Upload `6_CSE321_2026_Ch 11 Indexing.pdf` to `rag_agent`.
2. Preserve or rename the RAG document title to `cse321_indexing_live`.
3. Run live eval with `PROBLEM_AGENT_LIVE_EVAL_CASES=evals/live_materials/cse321_indexing_cases.jsonl`.

The suite contains:

- `cse321_indexing_btree_hard_short_answer`: the successful high-rigor short-answer case using B+ tree, sparse index, and disk I/O.
- `cse321_indexing_ordered_index_hard_mcq`: the high-rigor multiple-choice evidence-analysis case that previously failed strict quality checks, included intentionally to track MCQ stability.
- `cse321_indexing_control_medium_concept`: a medium concept-check control case.

The CSE321 cases use `golden_label_mode="partial"` because the listed `expected_chunk_ids` are representative must-have evidence chunks, not an exhaustive relevance judgment for the full lecture. Do not add `min_precision_at_k` for these partial labels. Prefer `hit_at_k`, `mrr_at_k`, and cited-evidence recall such as `min_cited_expected_chunk_recall`.

Use this short failure-analysis template when a CSE321 regression case fails:

```text
case_id:
execution_status:
failed_thresholds:
search_quality:
  hit_at_k:
  mrr_at_k:
  cited_expected_chunk_recall:
generation_quality:
  average_professor_grade_score:
  professor_score_band_counts:
  high_rigor_operation_counts:
  high_rigor_mc_choice_diagnostics_coverage:
reject_retry:
  reject_rate:
  actual_retry_count:
  top_rejection_categories:
manual_notes:
  - Was the exact RAG title cse321_indexing_live used?
  - Did the generated problem cite the expected evidence chunks?
  - For the ordered-index MCQ, did each distractor diagnose a distinct reasoning failure?
```

## Live Run

From `problem_agent/`:

1. Upload the lecture material to `rag_agent`.
2. Copy the exact RAG title/document id used for that upload.
3. Replace every `REPLACE_WITH_*` placeholder in `evals/live_materials/example_cases.jsonl`.
4. Export live eval environment variables.
5. Run `scripts/run_live_eval.sh`.

```bash
export PROBLEM_AGENT_LIVE_EVAL_ENABLED=true
export PROBLEM_AGENT_LIVE_EVAL_CASES=evals/live_materials/example_cases.jsonl
export PROBLEM_AGENT_LIVE_EVAL_OUTPUT_DIR=evals/reports
export PROBLEM_AGENT_LIVE_EVAL_COMPARE_BASELINE_SEARCH=true
export PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT=3
export RAG_AGENT_URL=http://localhost:8001
export OPENAI_API_KEY=...
./scripts/run_live_eval.sh
```

Fail the run when thresholds fail:

```bash
export PROBLEM_AGENT_LIVE_EVAL_FAIL_ON_THRESHOLD=true
./scripts/run_live_eval.sh
```

## Database Safety

Live eval writes benchmark-generated problems to an isolated SQLite DB by default:

```text
evals/reports/live_problem_generation_eval.sqlite
```

The runner ignores `DATABASE_URL` unless you explicitly opt in:

```bash
export PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL=true
```

Use that only for a disposable benchmark database. Local SQLite, `localhost`, and `127.0.0.1` DB hosts are accepted without an extra override. If `DATABASE_URL` contains `prod`/`production` or points to a non-local host, the runner raises unless this is also set:

```bash
export PROBLEM_AGENT_LIVE_EVAL_ALLOW_NONLOCAL_DATABASE=true
```

Do not use a production database for live eval.

Optional artifact publishing:

```bash
GENERATED_ARTIFACT_INDEX_URL=http://localhost:8000/generated-artifacts
GENERATED_ARTIFACT_ADD_URL=http://localhost:8000/add
```

The runner writes:

- `evals/reports/live_problem_generation_report.json`
- `evals/reports/live_problem_generation_cases.jsonl`
- `evals/reports/live_problem_generation_summary.md`
- `evals/reports/live_problem_generation_human_review.csv`
- `evals/reports/live_problem_generation_human_review_summary.json` when a filled review CSV is summarized
- `evals/reports/live_problem_generation_human_review_summary.md` when a filled review CSV is summarized

Each JSON report includes `report_schema_version`, `git_commit`, `cases_sha256`, and a safe `settings_snapshot`. Treat old reports as stale if the schema version is not the current `live_problem_generation_eval.v2`, if `cases_sha256` no longer matches the cases file, if the report was generated before the cases file was modified, or if it contains zero cases. Ignore stale reports and rerun the live benchmark before making product-quality claims.

If one case fails during search, generation, or DB work, the runner records that case as failed and continues with the remaining cases. The JSON and Markdown reports include `execution_status`, exception details, and any parsed rejection categories. When `PROBLEM_AGENT_LIVE_EVAL_FAIL_ON_THRESHOLD=true`, reports are still written before the command exits with a threshold failure.

## Human Review Export

The human review CSV is eval-only and intentionally includes private fields such as answer, explanation, rubric, and source evidence snapshot. It is not exposed through the student-facing API.

Use these blank columns for manual scoring:

- `reviewer_problem_quality_score`
- `reviewer_source_grounding_score`
- `reviewer_difficulty_fit_score`
- `reviewer_notes`

Reviewer scores may use either `0-1` or `1-5`; `1-5` scores are normalized to `0-1` during import. Suggested gates for commercial validation:

- average human problem quality `>= 0.75`
- average source grounding `>= 0.80`
- no answer correctness errors in `reviewer_notes`
- any professor-vs-human disagreement must be manually reviewed

The helper functions `load_human_review_csv`, `summarize_human_review`, and `write_human_review_summary` can import a filled CSV and produce JSON/Markdown summaries for calibration.

## Optional LLM Judge

You can add a separate LLM-as-judge pass to the live benchmark:

```bash
export PROBLEM_AGENT_LIVE_EVAL_LLM_JUDGE_ENABLED=true
export PROBLEM_AGENT_LIVE_EVAL_JUDGE_MODEL=gpt-5.5
export OPENAI_API_KEY=...
./scripts/run_live_eval.sh
```

The judge sees the generated question, choices, answer, explanation, rubric, source evidence snapshot, requested concepts, and requested difficulty/style. It writes aggregate judge metrics to the JSON/Markdown reports:

- `llm_judge_enabled`
- `average_llm_judge_overall_score`
- `llm_judge_action_counts`

Normal unit tests do not call the judge. If the judge is enabled for live eval, preflight requires `OPENAI_API_KEY`.
