# Current Data Pack RAG Upload Checklist

This checklist prepares the current data pack for live `problem_agent` validation. It does not modify `rag_agent`.

## Upload PDFs

Upload each PDF from `problem_agent/evals/source_materials/current_data_pack/` to `rag_agent`.

Use exactly these RAG titles/document IDs:

- `bio_gene_sequence_lecture10`
- `stats_discriminant_analysis`
- `physics_capacitance_dielectrics`
- `linguistics_discourse_genre`
- `nlp_transformers_cs224n`
- `ko_ml_sequence_rnn_cnn`
- `cv_detection_segmentation_cs231n`
- `econ_imperfect_competition_game_theory`
- `cpp_heap_destructors`

## Golden Labels

After upload:

1. Run `scripts/bootstrap_live_case_goldens.py`.
2. Manually review suggested chunk IDs and source spans.
3. Keep `golden_label_mode="partial"` unless you have exhaustively labeled all relevant chunks.
4. Do not set `min_precision_at_k` for partial labels.
5. Prefer `hit_at_k`, `mrr_at_k`, generation-context recall, and cited-evidence recall.

Example:

```bash
python scripts/bootstrap_live_case_goldens.py \
  --cases evals/live_materials/current_data_cases.jsonl \
  --out evals/live_materials/current_data_cases.suggested_goldens.jsonl \
  --rag-url "$RAG_AGENT_URL" \
  --top-k 8
```

## Run Order

1. Run unit tests: `./scripts/run_tests.sh`
2. Upload PDFs to `rag_agent`.
3. Bootstrap and review golden labels.
4. Run smoke benchmark with `evals/live_materials/current_data_smoke_cases.jsonl`.
5. Run full benchmark with `evals/live_materials/current_data_cases.jsonl`.

Do not claim product quality is verified until a live benchmark actually runs and the report is reviewed.
