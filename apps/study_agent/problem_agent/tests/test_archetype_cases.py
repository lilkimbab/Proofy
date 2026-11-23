import json
from pathlib import Path

from app.services.live_problem_generation_eval import load_live_problem_generation_cases


ARCHETYPE_CASES = Path("evals/live_materials/archetype_cases.jsonl")


def test_archetype_cases_parse_and_use_partial_labels():
    cases = load_live_problem_generation_cases(ARCHETYPE_CASES)

    assert len(cases) >= 8
    assert all(case.golden_label_mode == "partial" for case in cases)
    assert all(case.min_precision_at_k is None for case in cases)
    assert all(case.content_atom_type for case in cases)
    assert all(case.problem_kernel for case in cases)


def test_archetype_cases_cover_major_atom_and_kernel_families():
    cases = load_live_problem_generation_cases(ARCHETYPE_CASES)
    atom_types = {case.content_atom_type for case in cases}
    kernels = {case.problem_kernel for case in cases}

    assert {
        "formula",
        "rule",
        "procedure",
        "comparison",
        "evidence_claim",
        "condition_exception",
        "classification",
        "data_table",
    } <= atom_types
    assert {
        "compute_from_given",
        "diagnose_error",
        "trace_process",
        "compare_boundary",
        "evidence_to_claim",
        "condition_mutation",
        "apply_rule_to_case",
    } <= kernels


def test_archetype_cases_are_not_organized_by_single_domain():
    rows = [json.loads(line) for line in ARCHETYPE_CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    domain_families = {row["domain_family"] for row in rows}

    assert len(domain_families) >= 5
