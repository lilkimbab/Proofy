from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path("scripts/bootstrap_live_case_goldens.py")


def _load_bootstrap_module():
    spec = importlib.util.spec_from_file_location("bootstrap_live_case_goldens", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_case(path: Path, **overrides):
    row = {
        "id": "case_1",
        "document_id": "doc_1",
        "concepts": ["alpha"],
        "expected_search_terms": ["beta"],
        "expected_source_spans": [],
        "expected_chunk_ids": [],
        "golden_label_mode": "partial",
    }
    row.update(overrides)
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


def test_bootstrap_missing_rag_url_writes_unchanged_cases(tmp_path):
    module = _load_bootstrap_module()
    cases_path = tmp_path / "cases.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_case(cases_path)

    rows = module.bootstrap_cases(
        cases_path=cases_path,
        out_path=out_path,
        rag_url=None,
        top_k=8,
    )

    assert rows[0]["expected_chunk_ids"] == []
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8"))["expected_chunk_ids"] == []


def test_bootstrap_fake_rag_response_produces_suggested_goldens(tmp_path, monkeypatch):
    module = _load_bootstrap_module()
    cases_path = tmp_path / "cases.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_case(cases_path)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "results": [
                        {
                            "chunk_id": "chunk_a",
                            "content": "Alpha beta source evidence for the first suggested span.",
                        }
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr(module.urllib_request, "urlopen", lambda *args, **kwargs: FakeResponse())

    rows = module.bootstrap_cases(
        cases_path=cases_path,
        out_path=out_path,
        rag_url="http://localhost:8001",
        top_k=8,
    )

    assert rows[0]["expected_chunk_ids"] == ["chunk_a"]
    assert rows[0]["expected_source_spans"]
    assert "min_precision_at_k" not in rows[0]


def test_bootstrap_apply_preserves_existing_manual_chunk_ids(tmp_path, monkeypatch):
    module = _load_bootstrap_module()
    cases_path = tmp_path / "cases.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_case(cases_path, expected_chunk_ids=["manual_chunk"])

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"results":[{"chunk_id":"new_chunk","content":"new content span"}]}'

    monkeypatch.setattr(module.urllib_request, "urlopen", lambda *args, **kwargs: FakeResponse())

    module.bootstrap_cases(
        cases_path=cases_path,
        out_path=out_path,
        rag_url="http://localhost:8001",
        top_k=8,
        apply=True,
    )
    updated = json.loads(cases_path.read_text(encoding="utf-8"))

    assert updated["expected_chunk_ids"] == ["manual_chunk"]
    assert updated["golden_label_mode"] == "partial"
    assert "min_precision_at_k" not in updated
