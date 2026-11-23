from pathlib import Path

from app.schemas.problems import GenerateProblemRequest
from app.services.live_problem_generation_eval import load_live_problem_generation_cases


FULL_CASES_PATH = Path("evals/live_materials/current_data_cases.jsonl")
SMOKE_CASES_PATH = Path("evals/live_materials/current_data_smoke_cases.jsonl")
REVIEWED_FULL_CASES_PATH = Path("evals/live_materials/current_data_cases.reviewed.jsonl")
REVIEWED_SMOKE_CASES_PATH = Path("evals/live_materials/current_data_smoke_cases.reviewed.jsonl")
ACCOUNTING_DOCUMENT_ID = "ko_accounting_principles_appraiser_2026"


def _full_cases():
    return load_live_problem_generation_cases(FULL_CASES_PATH)


def test_current_data_case_files_parse():
    assert len(load_live_problem_generation_cases(FULL_CASES_PATH)) >= 20
    assert len(load_live_problem_generation_cases(SMOKE_CASES_PATH)) == 8


def test_current_data_cases_have_required_metadata_and_partial_labels():
    for case in _full_cases():
        assert case.document_id
        assert case.domain_family
        assert case.domain
        assert case.language in {"en", "ko"}
        assert case.golden_label_mode == "partial"
        assert case.min_precision_at_k is None
        assert case.expected_search_term_aliases is not None
        assert case.expected_problem_term_aliases is not None


def test_current_data_cases_request_values_validate():
    for case in _full_cases():
        request = GenerateProblemRequest.model_validate(
            {
                "document_id": case.document_id,
                "concepts": case.concepts,
                **case.request,
            }
        )
        assert request.document_id == case.document_id


def test_current_data_cases_include_question_type_and_rigor_balance():
    cases = _full_cases()
    problem_types = {case.request["type"] for case in cases}
    high_rigor_cases = [
        case for case in cases if case.request.get("target_rigor") == "high"
    ]
    medium_cases = [
        case for case in cases if case.request.get("target_rigor") == "standard"
    ]

    assert {"multiple_choice", "short_answer"} <= problem_types
    assert len([case for case in cases if case.request["type"] == "multiple_choice"]) >= 10
    assert len([case for case in cases if case.request["type"] == "short_answer"]) >= 10
    assert len(high_rigor_cases) >= 12
    assert len(medium_cases) >= 2
    for case in high_rigor_cases:
        assert case.request["quality_mode"] == "strict"
        assert case.request["difficulty"] == "hard"


def test_current_data_case_domain_coverage():
    domain_families = {case.domain_family for case in _full_cases()}

    assert {
        "biology",
        "statistics",
        "physics",
        "linguistics",
        "computer_science",
        "economics",
    } <= domain_families


def test_current_data_smoke_file_is_subset_of_full_case_ids():
    full_ids = {case.id for case in load_live_problem_generation_cases(FULL_CASES_PATH)}
    smoke_ids = {case.id for case in load_live_problem_generation_cases(SMOKE_CASES_PATH)}

    assert smoke_ids <= full_ids


def test_current_data_cases_exclude_accounting_material():
    for path in (FULL_CASES_PATH, SMOKE_CASES_PATH):
        for case in load_live_problem_generation_cases(path):
            assert case.document_id != ACCOUNTING_DOCUMENT_ID
            assert case.domain_family != "accounting"


def test_reviewed_current_data_case_files_parse_when_present():
    for path in (
        REVIEWED_FULL_CASES_PATH,
        REVIEWED_SMOKE_CASES_PATH,
    ):
        if not path.exists():
            continue
        cases = load_live_problem_generation_cases(path)
        assert cases
        for case in cases:
            assert case.golden_label_mode == "partial"
            assert case.min_precision_at_k is None
            assert case.document_id != ACCOUNTING_DOCUMENT_ID
            assert case.domain_family != "accounting"


def test_reviewed_high_rigor_cases_have_expected_chunk_ids_when_present():
    if not REVIEWED_FULL_CASES_PATH.exists():
        return

    for case in load_live_problem_generation_cases(REVIEWED_FULL_CASES_PATH):
        if case.request.get("target_rigor") == "high":
            assert case.expected_chunk_ids, case.id

