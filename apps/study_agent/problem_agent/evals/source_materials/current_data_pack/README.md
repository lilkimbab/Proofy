# Current Data Pack Source Materials

This directory is for local live-benchmark source PDFs. The PDFs and ZIP are ignored by git and should not be committed as source code.

## Expected Inputs

Place these files here when preparing or refreshing the current data benchmark pack:

- `data.zip`

## Extraction

From the repository root:

```bash
mkdir -p problem_agent/evals/source_materials/current_data_pack
cp /home/parkjune/data.zip problem_agent/evals/source_materials/current_data_pack/data.zip
unzip -j -o /home/parkjune/data.zip '*.pdf' -d problem_agent/evals/source_materials/current_data_pack
```

After extraction, upload each PDF to `rag_agent` using the document IDs listed in `evals/live_materials/CURRENT_DATA_UPLOAD_CHECKLIST.md`.
