import json
from pathlib import Path


FEEDBACK_SEED_PATH = Path("evals/feedback/current_data_feedback_seed.jsonl")
ACCOUNTING_DOCUMENT_ID = "ko_accounting_principles_appraiser_2026"


def _feedback_rows():
    return [
        json.loads(line)
        for line in FEEDBACK_SEED_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_current_data_feedback_seed_parses_and_has_minimum_cases():
    rows = _feedback_rows()

    assert len(rows) >= 9
    assert all(row["id"] for row in rows)


def test_current_data_feedback_seed_domain_coverage():
    domain_families = {row["domain_family"] for row in _feedback_rows()}

    assert {
        "computer_science",
        "statistics",
        "physics",
        "biology",
        "economics",
    } <= domain_families


def test_current_data_feedback_seed_expected_fields_are_present():
    for row in _feedback_rows():
        expected = row["expected"]
        assert "score_min" in expected
        assert "score_max" in expected
        assert expected["score_min"] <= expected["score_max"]
        assert expected["must_include_feedback_terms"]
        assert row["source_chunks"]
        assert row["problem"]
        assert row["submission"]


def test_current_data_feedback_seed_excludes_accounting_material():
    for row in _feedback_rows():
        assert row["domain_family"] != "accounting"
        assert row["document_id"] != ACCOUNTING_DOCUMENT_ID
